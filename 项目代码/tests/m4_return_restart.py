"""Full dependency restart followed by durable return command replay and invariants.
Pause all writers and finish the browser receipt/rejection first.
"""
import json,os,runpy
from datetime import datetime,timezone
os.environ['M4_RETURN_DATABASE']='fulfillment'
import m4_return_acceptance as base
from m1_acceptance import ROOT,sql
from m0_restart import snapshot
E={'run_at':datetime.now(timezone.utc).isoformat(),'checks':[]}
def check(name,ok,detail=None):
    E['checks'].append({'name':name,'passed':bool(ok),'detail':detail})
    if not ok:raise AssertionError(name+': '+str(detail))
base.check=check
try:
    os.environ['RESTART_EVIDENCE']='M4.2-restart.json'
    runpy.run_path(str(ROOT/'tests/m0_restart.py'),run_name='__main__')
    check('full dependencies preserve old and new return snapshots',json.loads((ROOT/'../学习资料/10-验收证据/M4.2-restart.json').read_text(encoding='utf-8'))['status']=='passed')
    fx=json.loads((ROOT/'../学习资料/10-验收证据/M4.2-ui-fixture.json').read_text(encoding='utf-8'));order=fx['order'];admin=base.Client(48080).login()
    received,rejected=sql('SELECT id,status,shipment_id,reason,rejection_reason FROM ful_return WHERE order_id=%s ORDER BY id',(order,))
    before=snapshot()
    for command,row in [('RETURN_CREATE',received),('RETURN_RECEIVE',received),('RETURN_REJECT',rejected)]:
        key,saved=sql("SELECT idempotency_key,response_json FROM ful_command_record WHERE actor_id=1 AND command_type=%s AND JSON_UNQUOTE(JSON_EXTRACT(response_json,'$.id'))=%s ORDER BY id LIMIT 1",(command,str(row[0])))[0]
        saved=json.loads(saved)
        if command=='RETURN_CREATE':
            lines=sql('SELECT shipment_item_id,quantity FROM ful_return_item WHERE return_id=%s ORDER BY id',(row[0],))
            result=admin.create_return(order,row[2],lines,key,extra={'reason':row[3]})
        elif command=='RETURN_RECEIVE':result=admin.receive(order,row[0],key)
        else:result=admin.reject(order,row[0],key,reason=row[4])
        check(command+' original persisted response after full restart',result==saved)
    check('replaying returns leaves all SQL facts and sequences unchanged',snapshot()==before)
    base.invariants()
    check('main history remains 0 through 4',tuple(x[0] for x in sql('SELECT version FROM ful_flyway_schema_history ORDER BY installed_rank'))==('0','1','2','3','4'))
    E['result']='passed'
except Exception as error:E['result']='failed';E['error']=str(error);raise
finally:
    (ROOT/'../学习资料/10-验收证据/M4.2-replay-after-restart.json').write_text(json.dumps(E,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
    print('M4.2 replay after restart',E.get('result'),len(E['checks']),'checks')
