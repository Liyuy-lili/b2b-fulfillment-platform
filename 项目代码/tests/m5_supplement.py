"""Final-artifact legacy regression, offline boot and durable Broker recovery.
Uses the already-passed isolated M5 schema/vhost. No main business writes.
"""
import hashlib,json,os,subprocess,sys,uuid
from datetime import datetime,timezone
import m5_acceptance as m
core=json.loads((m.ROOT/'../学习资料/10-验收证据/M5-acceptance.json').read_text(encoding='utf-8'))
m.DATABASE=m.VHOST=core['database'];os.environ['DB_NAME']=m.DATABASE
m.E={'run_at':datetime.now(timezone.utc).isoformat(),'database':m.DATABASE,'checks':[],'commands':[],'processes':[]}
E=m.E
try:
    m.check('passed isolated core and exact artifact',core['result']=='passed' and hashlib.sha256(m.JAR.read_bytes()).hexdigest()==core['artifact_sha256'])
    if os.getenv('M5_RESUME_AFTER_LEGACY')=='1':
        prior=json.loads((m.ROOT/'../学习资料/10-验收证据/M5-supplement-initial-2.json').read_text(encoding='utf-8'))
        m.check('retained legacy process provenance',prior['database']==m.DATABASE and all(any(c['name']=='legacy regression '+s and c['passed'] for c in prior['checks']) for s in ['m1_acceptance.py','m0_smoke.py']))
        for name,key in [('M5-M1-regression.json','result'),('M5-ERP-regression.json','status')]:
            saved=json.loads((m.ROOT/'../学习资料/10-验收证据'/name).read_text(encoding='utf-8'))
            m.check('retained final-artifact regression '+name,saved[key]=='passed' and all(c['passed'] for c in saved['checks']))
        E['resumed_after_legacy']=True
        E['legacy_execution_evidence']='M5-supplement-initial-2.json'
    else:
        api=m.start('supplement-api',48082)
        env=os.environ.copy();env['API_BASE']='http://127.0.0.1:48082'
        for script,var,name in [('m1_acceptance.py','M1_EVIDENCE','M5-M1-regression.json'),('m0_smoke.py','M0_EVIDENCE','M5-ERP-regression.json')]:
            env[var]=name
            with (m.ROOT/'.local'/('m5-'+script+'.log')).open('wb') as out:r=subprocess.run([sys.executable,str(m.ROOT/'tests'/script)],env=env,stdout=out,stderr=subprocess.STDOUT,timeout=180)
            m.check('legacy regression '+script,r.returncode==0)
        m.stop(api)
    # Workers really enabled while the Broker is unavailable, including boot.
    m.shell('scripts/Stop-Messaging.ps1')
    api=m.start('offline-boot',48082,True,True,('--fulfillment.messages.max-attempts=10',))
    c=m.Client(48082).login();m.check('enabled worker application authenticates while Broker down',True)
    f=m.b.Fixture(c,'OfflineBoot');fx=f.shipment('离线启动',('1',))
    m.check('business shipping succeeds while enabled transport offline',m.sql('SELECT COUNT(*) FROM ful_outbox_event WHERE order_id=%s',(fx['order'],))[0][0]==3)
    before=m.facts();m.shell('scripts/Start-Messaging.ps1')
    m.wait(lambda:m.sql("SELECT COUNT(*) FROM ful_outbox_event WHERE status<>'SENT'")[0][0]==0,150)
    m.wait(lambda:m.sql('SELECT COUNT(*) FROM ful_outbox_event o LEFT JOIN ful_inbox_event i ON i.tenant_id=o.tenant_id AND i.event_id=o.event_id WHERE i.id IS NULL OR i.status<>\'PROCESSED\'')[0][0]==0,150)
    m.check('restored Broker drains all genuine Outbox events',m.facts()==before)
    m.stop(api)
    # No consumer remains. Confirm a real canonical persistent message, then
    # restart the actual Broker process and assert the queued body survived.
    body=m.event_for(fx['order'],'SHIPMENT_CONFIRMED')[1]
    m.wait(lambda:m.queue_count()==0)
    m.put_messages([body]);m.check('confirmed persistent message queued without consumer',m.queue_count()==1)
    m.shell('scripts/Stop-Messaging.ps1');m.shell('scripts/Start-Messaging.ps1')
    m.check('durable queue survives actual Broker restart',m.queue_count()==1)
    ev=json.loads(body)['eventId'];old=m.sql('SELECT duplicate_count FROM ful_inbox_event WHERE event_id=%s',(ev,))[0][0]
    api=m.start('durability-consumer',48082,consumer=True)
    m.wait(lambda:m.sql('SELECT duplicate_count FROM ful_inbox_event WHERE event_id=%s',(ev,))[0][0]>old)
    m.check('restart redelivery deduplicated without business mutation',m.facts()==before)
    E['offline_fixture']=fx;E['artifact_sha256']=core['artifact_sha256'];E['result']='passed'
except Exception as error:E['result']='failed';E['error']=str(error);raise
finally:
    for p,out in m.OWNED:m.stop(p);out.close()
    E['all_owned_processes_stopped']=all(p.poll() is not None for p,_ in m.OWNED)
    (m.ROOT/'../学习资料/10-验收证据/M5-supplement.json').write_text(json.dumps(E,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
    print('M5 supplement',E.get('result'),len(E['checks']),'checks',flush=True)
