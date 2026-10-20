"""Complete main SQL/Redis/Broker/application restart and saved intent replay."""
import json,os,subprocess,sys,uuid
from datetime import datetime,timezone
import m5_acceptance as m
os.environ['DB_NAME']='fulfillment';m.DATABASE=m.VHOST='fulfillment'
E={'run_at':datetime.now(timezone.utc).isoformat(),'checks':[]}
def check(name,ok,detail=None):
    E['checks'].append({'name':name,'passed':bool(ok),'detail':detail})
    if not ok:raise AssertionError(name+': '+str(detail))
try:
    ui=json.loads((m.ROOT/'../学习资料/10-验收证据/M5-browser-SQL.json').read_text(encoding='utf-8'))
    check('browser actions verified first',ui['result']=='passed')
    rows=m.sql('SELECT a.action,a.event_id,a.reason,c.idempotency_key,c.response_json FROM ful_message_action a JOIN ful_command_record c ON c.tenant_id=a.tenant_id AND c.id=a.command_id WHERE a.order_id=%s ORDER BY a.id',(ui['order_id'],))
    check('exactly two saved browser command results',len(rows)==2)
    c=m.Client(48080).login();scan_key='m5-restart-'+uuid.uuid4().hex
    report=c.api('POST','/fulfillment/reconcile/run',{'scope':'TENANT'},headers={'Idempotency-Key':scan_key})
    check('main business audit clean before restart',report['differenceCount']==0,report)
    m.wait(lambda:m.sql("SELECT COUNT(*) FROM ful_outbox_event WHERE status<>'SENT'")[0][0]==0)
    m.wait(lambda:m.queue_count()==0)
    env=os.environ.copy();env['RESTART_EVIDENCE']='M5-restart.json'
    with (m.ROOT/'.local/m5-full-restart.log').open('wb') as out:r=subprocess.run([sys.executable,str(m.ROOT/'tests/m0_restart.py')],env=env,stdout=out,stderr=subprocess.STDOUT,timeout=240)
    check('complete dependency restart exits0',r.returncode==0)
    saved=json.loads((m.ROOT/'../学习资料/10-验收证据/M5-restart.json').read_text(encoding='utf-8'))
    check('SQL Redis five message tables exact across restart',saved['status']=='passed' and saved['before']==saved['after'] and all(t+'_facts' in saved['before'] for t in ['ful_outbox_event','ful_outbox_delivery','ful_inbox_event','ful_order_read_model','ful_message_action']))
    c=m.Client(48080).login();before=m.facts();counts=m.sql('SELECT (SELECT COUNT(*) FROM ful_message_action),(SELECT COUNT(*) FROM ful_outbox_delivery)')
    for action,event,reason,key,response in rows:
        path='/fulfillment/message/rebuild' if action=='REBUILD' else '/fulfillment/message/replay'
        body={'orderId':ui['order_id'],'reason':reason}
        if action!='REBUILD':body.update(eventId=event,action=action)
        result=c.api('POST',path,body,headers={'Idempotency-Key':key})
        check('original '+action+' key stable after full restart',result==json.loads(response))
    check('saved intent replay no new action or sending attempt',counts==m.sql('SELECT (SELECT COUNT(*) FROM ful_message_action),(SELECT COUNT(*) FROM ful_outbox_delivery)') and before==m.facts())
    check('saved reconcile key stable',c.api('POST','/fulfillment/reconcile/run',{'scope':'TENANT'},headers={'Idempotency-Key':scan_key})==report)
    check('new observation business facts still clean',c.api('POST','/fulfillment/reconcile/run',{'scope':'TENANT'},headers={'Idempotency-Key':uuid.uuid4().hex})['differenceCount']==0)
    E['report']=report;E['result']='passed'
except Exception as error:E['result']='failed';E['error']=str(error);raise
finally:
    (m.ROOT/'../学习资料/10-验收证据/M5-replay-after-restart.json').write_text(json.dumps(E,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
    print('M5 full restart/replay',E.get('result'),len(E['checks']),'checks',flush=True)
