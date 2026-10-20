"""Read-only database verification of the scenario operated through the real browser."""
import json
from datetime import datetime,timezone
from m1_acceptance import ROOT,sql
f=json.loads((ROOT/'../学习资料/10-验收证据/M3-ui-fixture.json').read_text(encoding='utf-8'));e={'run_at':datetime.now(timezone.utc).isoformat(),'checks':[],'fixture':'M3-ui-fixture.json'}
def check(name,ok,detail=None):
    e['checks'].append({'name':name,'passed':bool(ok),'detail':detail})
    if not ok:raise AssertionError(name+': '+str(detail))
try:
    quantities=sql('SELECT ordered_qty,open_qty,reserved_qty,shipped_qty,cancelled_qty,status FROM ful_order_item i JOIN ful_order o ON o.id=i.order_id WHERE i.id=%s',(f['item'],))[0]
    check('browser order is 10 = 4 shipped + 6 cancelled',quantities[:5]==(10,0,0,4,6) and quantities[5]=='PARTIALLY_CLOSED',quantities)
    stock=sql('SELECT warehouse_id,`count`,ful_reserved_count FROM erp_stock WHERE tenant_id=1 AND product_id=%s ORDER BY warehouse_id',(f['product'],))
    check('browser final physical and reserved stock',stock==((int(f['warehouses'][0]['id']),2,0),(int(f['warehouses'][1]['id']),8,0)),stock)
    shipments=sql('SELECT id,shipment_no,erp_sale_out_id,status FROM ful_shipment WHERE order_id=%s',(f['order'],))
    check('one browser shipment delivered',len(shipments)==1 and shipments[0][3]=='DELIVERED',shipments)
    shipment=shipments[0]
    out=sql('SELECT status,total_count FROM erp_sale_out WHERE id=%s',(shipment[2],))[0]
    check('browser ERP out approved once for four',out==(20,4),out)
    physical=sql('SELECT `count` FROM erp_stock_record WHERE product_id=%s AND biz_type=50',(f['product'],))
    check('one physical deduction from browser action',physical==((-4,),),physical)
    check('browser cancellation facts retained',sql('SELECT quantity,reason FROM ful_cancellation WHERE order_id=%s',(f['order'],))==((6,'客户调整采购计划，取消剩余六件'),))
    callbacks=sql('SELECT event_type,result FROM ful_callback_event WHERE shipment_id=%s ORDER BY id',(shipment[0],))
    check('browser actual HTTP callbacks persisted',callbacks==(('IN_TRANSIT','RECORDED_IN_TRANSIT'),('DELIVERED','DELIVERED')),callbacks)
    e['screenshot_desktop']='M3-ui-desktop.jpg';e['screenshot_mobile']='M3-ui-mobile.jpg';e['desktop_css_viewport']={'width':1280,'height':900};e['mobile_observed_css_viewport']={'width':355,'height':767};e['browser_viewport_override_restored']=True;e['result']='passed'
finally:
    (ROOT/'../学习资料/10-验收证据/M3-ui-result.json').write_text(json.dumps(e,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
    print('M3 browser facts',e.get('result'),len(e['checks']),'checks')
