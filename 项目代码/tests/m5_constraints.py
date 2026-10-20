"""Rollback-only negative probes; never run against the main schema."""
import json,os
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
core=json.loads((ROOT/'../学习资料/10-验收证据/M5-acceptance.json').read_text(encoding='utf-8'))
os.environ['DB_NAME']=core['database']
from m1_acceptance import sql,db
E={'run_at':datetime.now(timezone.utc).isoformat(),'database':core['database'],'checks':[]}
def check(name,ok,detail=None):
    E['checks'].append({'name':name,'passed':bool(ok),'detail':detail})
    if not ok:raise AssertionError(name+': '+str(detail))
try:
    check('only passed isolated M5 schema',core['result']=='passed' and core['database'].startswith('fulfillment_m5_'))
    event=sql('SELECT id,event_id FROM ful_outbox_event ORDER BY id LIMIT 1')[0]
    inbox=sql('SELECT id FROM ful_inbox_event ORDER BY id LIMIT 1')[0][0]
    model=sql('SELECT id FROM ful_order_read_model ORDER BY id LIMIT 1')[0][0]
    action=sql('SELECT id FROM ful_message_action ORDER BY id LIMIT 1')[0][0]
    tables=['ful_outbox_event','ful_outbox_delivery','ful_inbox_event','ful_order_read_model','ful_message_action']
    before={t:sql('SELECT * FROM '+t+' ORDER BY id') for t in tables}
    probes=[('Outbox same-tenant FK','UPDATE ful_outbox_event SET order_id=999999 WHERE id=%s',(event[0],),1452),
      ('Outbox invalid state',"UPDATE ful_outbox_event SET status='UNKNOWN' WHERE id=%s",(event[0],),3819),
      ('Outbox malformed JSON',"UPDATE ful_outbox_event SET body='broken' WHERE id=%s",(event[0],),3819),
      ('Outbox payload version','UPDATE ful_outbox_event SET payload_version=99 WHERE id=%s',(event[0],),3819),
      ('Inbox same-tenant FK','UPDATE ful_inbox_event SET tenant_id=999999 WHERE id=%s',(inbox,),1452),
      ('Inbox invalid state',"UPDATE ful_inbox_event SET status='SENT' WHERE id=%s",(inbox,),3819),
      ('Inbox negative duplicates','UPDATE ful_inbox_event SET duplicate_count=-1 WHERE id=%s',(inbox,),3819),
      ('read-model invalid JSON',"UPDATE ful_order_read_model SET snapshot_json='broken' WHERE id=%s",(model,),3819),
      ('action empty reason',"UPDATE ful_message_action SET reason=' ' WHERE id=%s",(action,),3819),
      ('action invalid intent',"UPDATE ful_message_action SET action='RESHIP' WHERE id=%s",(action,),3819)]
    for name,query,args,expected in probes:
        code=None
        with db() as con:
            con.autocommit(False)
            try:
                with con.cursor() as cur:cur.execute(query,args)
            except Exception as error:code=error.args[0]
            finally:con.rollback()
        check('database rejects '+name,code==expected,{'actual':code,'expected':expected})
    check('all five tables unchanged after probes',before=={t:sql('SELECT * FROM '+t+' ORDER BY id') for t in tables})
    E['result']='passed'
except Exception as error:E['result']='failed';E['error']=str(error);raise
finally:
    (ROOT/'../学习资料/10-验收证据/M5-constraints.json').write_text(json.dumps(E,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('M5 constraints',E.get('result'),len(E['checks']),'checks')
