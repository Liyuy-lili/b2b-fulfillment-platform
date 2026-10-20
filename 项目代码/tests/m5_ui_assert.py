"""Read-only verification after real browser republish and projection rebuild."""
import hashlib,json,os
from datetime import datetime,timezone
import m5_acceptance as m
os.environ['DB_NAME']='fulfillment'
demo=json.loads((m.ROOT/'../学习资料/10-验收证据/M5-main-demo.json').read_text(encoding='utf-8'))
E={'run_at':datetime.now(timezone.utc).isoformat(),'checks':[]}
def check(name,ok,detail=None):
    E['checks'].append({'name':name,'passed':bool(ok),'detail':detail})
    if not ok:raise AssertionError(name+': '+str(detail))
try:
    order=demo['fixture']['order'];ev=demo['event_id']
    m.wait(lambda:m.sql('SELECT status FROM ful_outbox_event WHERE event_id=%s',(ev,))==(('SENT',),))
    m.wait(lambda:m.sql('SELECT duplicate_count FROM ful_inbox_event WHERE event_id=%s',(ev,))[0][0]>=1)
    check('17 business tables identical across browser message actions',hashlib.sha256(json.dumps(m.facts(),default=str,sort_keys=True).encode()).hexdigest()==demo['before_browser_digest'])
    actions=m.sql('SELECT action,reason,outcome,actor_id FROM ful_message_action WHERE order_id=%s ORDER BY id',(order,))
    check('two real browser actions with reason actor audit',len(actions)==2 and [r[0] for r in actions]==['REPUBLISH','REBUILD'] and all(r[1] and r[3]==1 for r in actions),actions)
    check('same immutable event published twice',m.sql('SELECT COUNT(*),MIN(event_id),MAX(event_id) FROM ful_outbox_delivery WHERE event_id=%s',(ev,))==((2,ev,ev),))
    check('one Inbox records duplicate redelivery',m.sql('SELECT COUNT(*),MIN(duplicate_count) FROM ful_inbox_event WHERE event_id=%s',(ev,))[0][0]==1)
    check('rebuild current version no fabricated events',m.sql('SELECT COUNT(*) FROM ful_outbox_event WHERE order_id=%s',(order,))[0][0]==5 and m.sql('SELECT m.observed_version=o.version FROM ful_order_read_model m JOIN ful_order o ON o.tenant_id=m.tenant_id AND o.id=m.order_id WHERE o.id=%s',(order,))==((1,),))
    E['order_id']=order;E['event_id']=ev;E['result']='passed'
except Exception as error:E['result']='failed';E['error']=str(error);raise
finally:
    (m.ROOT/'../学习资料/10-验收证据/M5-browser-SQL.json').write_text(json.dumps(E,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
    print('M5 browser SQL',E.get('result'),len(E['checks']),'checks')
