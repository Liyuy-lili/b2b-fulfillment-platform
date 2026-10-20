"""Full local dependency restart + replay saved M2 commands. Pause business writes first."""
import json,os,runpy
from m2_acceptance import M2Client
from m1_acceptance import ROOT,sql

E={'date':'2026-10-18','checks':[]}
def check(name,ok,detail=None):
    E['checks'].append({'name':name,'passed':bool(ok),'detail':detail})
    if not ok:raise AssertionError(name+': '+str(detail))
try:
    os.environ['RESTART_EVIDENCE']='M2-restart.json'
    runpy.run_path(str(ROOT/'tests/m0_restart.py'),run_name='__main__')
    admin=M2Client().login();fixture=json.loads((ROOT/'../学习资料/10-验收证据/M2-acceptance.json').read_text(encoding='utf-8'))['ids']
    rows=sql("SELECT idempotency_key,response_json FROM ful_command_record WHERE tenant_id=1 AND actor_id=1 AND command_type='ALLOCATE' AND JSON_UNQUOTE(JSON_EXTRACT(response_json,'$.orderId'))=%s ORDER BY id LIMIT 1",(fixture['hold_order'],))
    key,saved=rows[0];saved=json.loads(saved)
    check('allocated command replays after full dependency restart',admin.allocate(fixture['hold_order'],[fixture['warehouse_a']],key=key)==saved)
    key,saved=sql("SELECT idempotency_key,response_json FROM ful_command_record WHERE tenant_id=1 AND actor_id=1 AND command_type='RELEASE' AND idempotency_key LIKE 'full%%' ORDER BY id DESC LIMIT 1")[0]
    saved=json.loads(saved)
    lines=[(line['reservationId'],line['quantity']) for line in saved['released']]
    check('released command replays original outcome after restart',admin.release(saved['orderId'],lines,key=key)==saved)
    mismatches=sql('SELECT s.id FROM erp_stock s WHERE s.`count`<s.ful_reserved_count OR s.ful_reserved_count<0 OR s.ful_reserved_count<>(SELECT COALESCE(SUM(r.held_qty),0) FROM ful_reservation r WHERE r.tenant_id=s.tenant_id AND r.product_id=s.product_id AND r.warehouse_id=s.warehouse_id) OR s.ful_reserved_count<>(SELECT COALESCE(SUM(l.held_delta),0) FROM ful_stock_ledger l WHERE l.tenant_id=s.tenant_id AND l.product_id=s.product_id AND l.warehouse_id=s.warehouse_id)')
    check('all main database H R held and reservation deltas consistent',not mismatches,mismatches)
    missing=sql('SELECT r.id FROM ful_reservation r LEFT JOIN erp_stock s ON s.tenant_id=r.tenant_id AND s.product_id=r.product_id AND s.warehouse_id=r.warehouse_id WHERE r.held_qty>0 AND s.id IS NULL')
    check('no commitment without physical stock identity',not missing,missing)
    physical=sql('SELECT s.id FROM erp_stock s WHERE s.`count`<>(SELECT COALESCE(SUM(l.`count`),0) FROM erp_stock_record l WHERE l.tenant_id=s.tenant_id AND l.product_id=s.product_id AND l.warehouse_id=s.warehouse_id)')
    check('all physical balances match ERP delta sums',not physical,physical)
    E['result']='passed'
except Exception as exc:E['result']='failed';E['error']=str(exc);raise
finally:
    (ROOT/'../学习资料/10-验收证据/M2-replay-after-restart.json').write_text(json.dumps(E,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
    print('M2 replay after restart',E.get('result'),len(E['checks']),'checks')
