"""Read-only SQL checks after real browser scan and review. No UI simulation."""
import json,os
from datetime import datetime,timezone
from m4_reconcile_ui_runtime import ROOT,META,digest
data=json.loads(META.read_text(encoding='utf-8'));os.environ['DB_NAME']=data['database']
from m1_acceptance import sql
E={'run_at':datetime.now(timezone.utc).isoformat(),'database':data['database'],'checks':[]}
def check(name,ok,detail=None):
    E['checks'].append({'name':name,'passed':bool(ok),'detail':detail})
    if not ok:raise AssertionError(name+': '+str(detail))
try:
    check('browser created new clean report',sql('SELECT difference_count,scanned_count FROM ful_reconcile_run WHERE id=22')==((0,123),))
    notes=sql("SELECT id,run_id,item_id,actor_id,note FROM ful_reconcile_review WHERE note=%s",('浏览器验收：已核实为独立测试库注入，原报告保留，库存事实已在测试恢复。',))
    check('one real browser review persisted',len(notes)==1 and notes[0][1:4]==(3,3,1),notes)
    check('browser review acknowledgement saved',sql('SELECT resolution_status FROM ful_reconcile_item WHERE id=3')==(('ACKNOWLEDGED',),))
    check('original expected actual unchanged',sql('SELECT expected_value,actual_value FROM ful_reconcile_item WHERE id=3')==(('0.000000','1.000000'),))
    check('historical dirty report remains two differences',sql('SELECT difference_count FROM ful_reconcile_run WHERE id=3')==((2,),))
    check('all isolated business facts unchanged by browser actions',digest(data['database'])==data['before_core_digest'])
    check('all main business facts unchanged during isolated UI checks',digest('fulfillment')==data['before_main_digest'])
    E['result']='passed'
except Exception as error:E['result']='failed';E['error']=str(error);raise
finally:
    (ROOT/'../学习资料/10-验收证据/M4.3-ui-result.json').write_text(json.dumps(E,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
    print('M4.3 browser SQL',E.get('result'),len(E['checks']),'checks')
