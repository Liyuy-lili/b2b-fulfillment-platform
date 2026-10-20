"""Full dependency restart and durable SHIP/CANCEL/callback replay; run after pausing all writers."""
import json,os,runpy
from datetime import datetime,timezone
from m1_acceptance import ROOT,sql
from m3_acceptance import M3Client,callback
E={'run_at':datetime.now(timezone.utc).isoformat(),'checks':[]}
def check(name,ok,detail=None):
    E['checks'].append({'name':name,'passed':bool(ok),'detail':detail})
    if not ok:raise AssertionError(name+': '+str(detail))
try:
    os.environ['RESTART_EVIDENCE']='M3-restart.json';runpy.run_path(str(ROOT/'tests/m0_restart.py'),run_name='__main__')
    admin=M3Client().login();f=json.loads((ROOT/'../学习资料/10-验收证据/M3-acceptance.json').read_text(encoding='utf-8'))['ids'];shipment=f['shipment']
    key,saved=sql("SELECT idempotency_key,response_json FROM ful_command_record WHERE command_type='SHIP' AND JSON_UNQUOTE(JSON_EXTRACT(response_json,'$.shipmentId'))=%s",(shipment['shipmentId'],))[0]
    saved=json.loads(saved);r=sql('SELECT reservation_id,quantity FROM ful_shipment_item WHERE shipment_id=%s',(shipment['shipmentId'],))
    check('SHIP replays original result after full restart',admin.ship(f['order'],f['warehouse_a'],r,key)==saved)
    key,saved=sql("SELECT idempotency_key,response_json FROM ful_command_record WHERE command_type='CANCEL' AND JSON_UNQUOTE(JSON_EXTRACT(response_json,'$.orderId'))=%s ORDER BY id DESC LIMIT 1",(f['order'],))[0]
    saved=json.loads(saved)
    check('CANCEL replays original result after full restart',admin.cancel(f['order'],[(x['id'],x['quantity']) for x in saved['cancelled']],key)==saved)
    event,occurred=sql("SELECT event_id,occurred_at FROM ful_callback_event WHERE shipment_id=%s AND event_type='DELIVERED' ORDER BY id LIMIT 1",(shipment['shipmentId'],))[0]
    before=sql('SELECT id,`count`,ful_reserved_count FROM erp_stock ORDER BY id')
    response,_=callback(shipment['shipmentNo'],event=event,occurred=occurred.isoformat()+'+00:00')
    check('callback replay after restart returns saved delivery',response['code']==0 and response['data']['outcome']=='DELIVERED',response)
    check('replaying commands and callback changes no stock',before==sql('SELECT id,`count`,ful_reserved_count FROM erp_stock ORDER BY id'))
    bad=sql('SELECT s.id FROM erp_stock s WHERE s.`count`<s.ful_reserved_count OR s.ful_reserved_count<0 OR s.ful_reserved_count<>(SELECT COALESCE(SUM(r.held_qty),0) FROM ful_reservation r WHERE r.tenant_id=s.tenant_id AND r.product_id=s.product_id AND r.warehouse_id=s.warehouse_id) OR s.ful_reserved_count<>(SELECT COALESCE(SUM(l.held_delta),0) FROM ful_stock_ledger l WHERE l.tenant_id=s.tenant_id AND l.product_id=s.product_id AND l.warehouse_id=s.warehouse_id) OR s.`count`<>(SELECT COALESCE(SUM(l.`count`),0) FROM erp_stock_record l WHERE l.tenant_id=s.tenant_id AND l.product_id=s.product_id AND l.warehouse_id=s.warehouse_id)')
    check('all tenants stock agrees with reservations and both ledgers',not bad,bad)
    bad=sql('SELECT i.id FROM ful_order_item i WHERE i.reserved_qty<>(SELECT COALESCE(SUM(r.held_qty),0) FROM ful_reservation r WHERE r.tenant_id=i.tenant_id AND r.order_item_id=i.id) OR i.shipped_qty<>(SELECT COALESCE(SUM(si.quantity),0) FROM ful_shipment_item si WHERE si.tenant_id=i.tenant_id AND si.order_item_id=i.id) OR i.cancelled_qty<>(SELECT COALESCE(SUM(c.quantity),0) FROM ful_cancellation c WHERE c.tenant_id=i.tenant_id AND c.order_item_id=i.id)')
    check('all order aggregates agree with commitment shipment and cancellation facts',not bad,bad)
    bad=sql('SELECT r.id FROM ful_reservation r WHERE r.consumed_qty<>(SELECT COALESCE(SUM(si.quantity),0) FROM ful_shipment_item si WHERE si.tenant_id=r.tenant_id AND si.reservation_id=r.id)')
    check('all consumed quantities agree with shipment facts',not bad,bad)
    bad=sql('SELECT s.id FROM ful_shipment s LEFT JOIN erp_sale_out e ON e.tenant_id=s.tenant_id AND e.id=s.erp_sale_out_id WHERE e.id IS NULL OR e.status<>20 OR e.deleted<>0')
    check('all shipments link an approved same-tenant ERP out',not bad,bad)
    E['result']='passed'
except Exception as exc:E['result']='failed';E['error']=str(exc);raise
finally:
    (ROOT/'../学习资料/10-验收证据/M3-replay-after-restart.json').write_text(json.dumps(E,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
    print('M3 replay after restart',E.get('result'),len(E['checks']),'checks')
