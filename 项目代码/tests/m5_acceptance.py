"""Whole M5 real MySQL/RabbitMQ/two-JVM acceptance. Isolated schema/vhost.
Business fixtures via HTTP. SQL changes only documented expiry/scheduling/read-model
test fixtures; no main inventory writes. Failed runs and owned logs are retained.
"""
import concurrent.futures,hashlib,json,os,shutil,socket,subprocess,time,uuid
from datetime import datetime,timezone
from decimal import Decimal as D
from urllib.parse import quote
import pika,requests
DATABASE='fulfillment_m5_'+datetime.now().strftime('%Y%m%d_%H%M%S')
os.environ['DB_NAME']=DATABASE;os.environ['M4_RETURN_DATABASE']=DATABASE
import m4_return_acceptance as b
from m1_acceptance import ROOT,sql,db
RUN='M5'+uuid.uuid4().hex[:8];VHOST=DATABASE
JAR=ROOT/'.local/m5-test.jar';OWNED=[];AUTH=('fulfillment','fulfillment-mq-dev')
E={'run_at':datetime.now(timezone.utc).isoformat(),'database':DATABASE,'vhost':VHOST,'redis_database':7,'checks':[],'commands':[],'processes':[],'fixtures':{},'injections':[]}
def check(name,ok,detail=None):
    E['checks'].append({'name':name,'passed':bool(ok),'detail':detail});print(('PASS ' if ok else 'FAIL ')+name,flush=True)
    if not ok:raise AssertionError(name+': '+str(detail))
b.check=check
def wait(fn,seconds=90):return b.wait_for(fn,seconds)
def shell(file,*args):
    path=ROOT/'.local'/('m5-command-'+DATABASE+'-'+str(os.getpid())+'-'+str(len(E['commands']))+'.log')
    with path.open('wb') as out:r=subprocess.run([os.environ['M0_PWSH'],'-NoProfile','-File',str(ROOT/file),*args],cwd=ROOT,stdout=out,stderr=subprocess.STDOUT,timeout=180)
    E['commands'].append({'script':file,'arguments':args,'exit_code':r.returncode,'log':str(path.relative_to(ROOT))});check('command '+file+' '+str(args),r.returncode==0)
def start(label,port=48083,publisher=False,consumer=False,test=()):
    env=os.environ.copy();env['APP_PORT']=str(port)
    out=(ROOT/'.local'/('m5-'+label+'-out.log')).open('wb')
    args=[shutil.which('java'),'-Xms128m','-Xmx768m','-Dfile.encoding=UTF-8','-Duser.timezone=Asia/Shanghai','-jar',str(JAR),'--spring.profiles.active=fulfillment'+(',fulfillment-message-test' if test else ''),'--spring.data.redis.database=7','--fulfillment.messages.enabled='+str(publisher or consumer).lower(),'--fulfillment.messages.publisher-enabled='+str(publisher).lower(),'--fulfillment.messages.consumer-enabled='+str(consumer).lower(),'--fulfillment.messages.virtual-host='+VHOST,'--fulfillment.messages.batch-size=1','--fulfillment.messages.lease-seconds=5','--fulfillment.messages.retry-base-ms=200','--fulfillment.messages.max-attempts=3','--fulfillment.messages.initial-delay-ms=1000','--fulfillment.messages.delay-ms=200','--fulfillment.expiry.delay-ms=1000','--logging.file.name=../.local/m5-'+label+'-app.log',*test]
    # Spring combines duplicate CLI property values into a comma-separated
    # string; test overrides replace defaults instead of appending duplicates.
    if test:
        overrides={x.split('=',1)[0] for x in test}
        args=[x for x in args[:-len(test)] if x.split('=',1)[0] not in overrides]+list(test)
    p=subprocess.Popen(args,cwd=ROOT/'backend',env=env,stdout=out,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW);OWNED.append((p,out));E['processes'].append({'label':label,'port':port,'pid':p.pid,'publisher':publisher,'consumer':consumer,'test_options':test})
    def ready():
        if p.poll() is not None:
            if p.returncode in (71,72) and any('message-crash=' in x for x in test):return True
            raise AssertionError('JVM exited before readiness '+label+' '+str(p.returncode))
        try:return Client(port).login()
        except Exception:return False
    wait(ready);return p
def stop(p):b.stop(p)
class Client(b.Client):
    def events(self,order,ok=True,**params):return self.api('GET','/fulfillment/message/page',params={'orderId':str(order),'pageSize':50,**params},ok=ok)
    def event(self,order,event,ok=True):return self.api('GET','/fulfillment/message/get',params={'orderId':str(order),'eventId':event},ok=ok)
    def replay(self,order,event,action='REPUBLISH',key=None,ok=True,reason='M5受控恢复'):
        return self.api('POST','/fulfillment/message/replay',{'orderId':str(order),'eventId':event,'action':action,'reason':reason},headers={'Idempotency-Key':key or uuid.uuid4().hex},ok=ok)
    def rebuild(self,order,key=None,ok=True):return self.api('POST','/fulfillment/message/rebuild',{'orderId':str(order),'reason':'M5读模型重建验证'},headers={'Idempotency-Key':key or uuid.uuid4().hex},ok=ok)
def event_for(order,kind):return sql('SELECT event_id,body FROM ful_outbox_event WHERE order_id=%s AND event_type=%s ORDER BY id DESC LIMIT 1',(order,kind))[0]
def event_status(event):return sql('SELECT status,lease_version FROM ful_outbox_event WHERE event_id=%s',(event,))[0]
def facts():
    tables=['erp_stock','erp_stock_record','ful_order','ful_order_item','ful_reservation','ful_stock_ledger','ful_shipment','ful_shipment_item','ful_cancellation','ful_return','ful_return_item','erp_sale_order','erp_sale_order_items','erp_sale_out','erp_sale_out_items','erp_sale_return','erp_sale_return_items']
    return {t:sql('SELECT * FROM '+t+' ORDER BY id') for t in tables}
def connection():return pika.BlockingConnection(pika.ConnectionParameters('127.0.0.1',35672,VHOST,pika.PlainCredentials(*AUTH),heartbeat=10,blocked_connection_timeout=3))
def put_messages(bodies):
    with connection() as con:
        ch=con.channel();ch.confirm_delivery()
        for body in bodies:ch.basic_publish('fulfillment.m5.exchange','events',body.encode() if isinstance(body,str) else body,pika.BasicProperties(delivery_mode=2,content_type='application/json'),mandatory=True)
def queue_count(dead=False):
    with connection() as con:return con.channel().queue_declare('fulfillment.m5.dead' if dead else 'fulfillment.m5.orders',passive=True).method.message_count
def due_only(event):
    sql("UPDATE ful_outbox_event SET next_attempt_at=TIMESTAMPADD(DAY,1,UTC_TIMESTAMP(6)) WHERE status IN ('NEW','RETRY_WAIT')")
    sql('UPDATE ful_outbox_event SET next_attempt_at=UTC_TIMESTAMP(6) WHERE event_id=%s',(event,));E['injections'].append({'kind':'dispatch_due_fixture','only_event':event})
def log_has(label,value):return value in (ROOT/'.local'/('m5-'+label+'-out.log')).read_text(encoding='utf-8',errors='replace')

def main():
    for port in [48082,48083]:
        with socket.socket() as s:check('test port free '+str(port),s.connect_ex(('127.0.0.1',port))!=0)
    shell('scripts/Start-Messaging.ps1')
    q=quote(VHOST,safe='');base='http://127.0.0.1:35673/api'
    r=requests.put(base+'/vhosts/'+q,auth=AUTH,json={},timeout=10);check('isolated RabbitMQ vhost created',r.status_code in [201,204])
    r=requests.put(base+'/permissions/'+q+'/fulfillment',auth=AUTH,json={'configure':'.*','write':'.*','read':'.*'},timeout=10);check('isolated vhost permission configured',r.status_code in [201,204])
    shell('scripts/Initialize-Database.ps1','-Database',DATABASE)
    for action in ['baseline','migrate','validate']:shell('scripts/Migrate-Database.ps1','-Action',action,'-Database',DATABASE)
    shutil.copyfile(ROOT/'backend/yudao-server/target/yudao-server.jar',JAR);E['artifact_sha256']=hashlib.sha256(JAR.read_bytes()).hexdigest()
    a=start('api',48082);c=Client(48082).login();f=b.Fixture(c,'All')
    failure=start('append-fault',test=('--fulfillment.test.message-append-failure=true',))
    fx=f.shipment('事件闭环',('2.000001',),ordered='6.000001');E['fixtures']['flow']=fx
    # It was partially shipped then cancelled by the existing fixture helper.
    initial=sql('SELECT COUNT(*) FROM ful_outbox_event')[0][0]
    check('bound allocate shipment cancel emitted four events',initial==4)
    receive=c.create_return(fx['order'],fx['shipment'],[(fx['lines'][0]['id'],'1.000001')]);c.receive(fx['order'],receive['id'])
    before_event=sql('SELECT COUNT(*) FROM ful_outbox_event')[0][0];c.receive(fx['order'],receive['id'])
    check('already received new key emits no duplicate event',sql('SELECT COUNT(*) FROM ful_outbox_event')[0][0]==before_event)
    # A fresh order remains reserved; fail only after ERP+fulfillment+Outbox writes.
    source=c.create('sale-order',{'customerId':f.customer,'accountId':f.account,'orderTime':b.NOW,'discountPercent':'0','items':[{'productId':fx['product'],'count':'3','productPrice':'2','taxPercent':'0'}]});c.approve('sale-order',source)
    key='bind-'+RUN
    with concurrent.futures.ThreadPoolExecutor(6) as pool:bound=list(pool.map(lambda n:Client(48082 if n%2 else 48083).login().bind(source,key),range(6)))
    order=bound[0]['orderId'];check('six cross-JVM bind requests one event',len({v['orderId'] for v in bound})==1 and sql('SELECT COUNT(*) FROM ful_outbox_event WHERE order_id=%s',(order,))[0][0]==1)
    held=c.allocate(order,[f.w])['reservations'][0];before=facts();count=sql('SELECT COUNT(*) FROM ful_outbox_event')[0][0];shipkey='fault-ship-'+RUN
    result=Client(48083).login().ship(order,f.w,[(held['id'],'1')],shipkey,False)
    check('after-Outbox fault rejects shipment',result['code']!=0)
    check('ERP H R facts and event all roll back',facts()==before and sql('SELECT COUNT(*) FROM ful_outbox_event')[0][0]==count)
    check('failed shipment command not retained',not sql("SELECT id FROM ful_command_record WHERE command_type='SHIP' AND idempotency_key=%s",(shipkey,)))
    shipped=c.ship(order,f.w,[(held['id'],'1')],shipkey);c.ship(order,f.w,[(held['id'],'1')],shipkey)
    check('same-key healthy retry exactly one event',sql("SELECT COUNT(*) FROM ful_outbox_event WHERE order_id=%s AND event_type='SHIPMENT_CONFIRMED'",(order,))[0][0]==1)
    c.release(order,[(held['id'],'1')]);sql('UPDATE ful_reservation SET expire_at=TIMESTAMPADD(SECOND,-1,UTC_TIMESTAMP(6)) WHERE id=%s',(held['id'],));E['injections'].append({'kind':'expiry_deadline','reservation':held['id']})
    wait(lambda:bool(sql("SELECT id FROM ful_outbox_event WHERE order_id=%s AND event_type='RESERVATION_EXPIRED'",(order,))))
    check('expiry event shares system actor command',sql("SELECT c.actor_id FROM ful_outbox_event e JOIN ful_command_record c ON c.id=e.command_id WHERE e.order_id=%s AND e.event_type='RESERVATION_EXPIRED'",(order,))==((0,),))
    c.cancel(order,[(c.api('GET','/fulfillment/order/get',params={'id':order})['items'][0]['id'],'2')]);c.allocate(order,[f.w])
    types={x[0] for x in sql('SELECT DISTINCT event_type FROM ful_outbox_event')};check('all eight declared business event types exercised',types=={'ORDER_BOUND','STOCK_RESERVED','ALLOCATION_ATTEMPTED','STOCK_RELEASED','SHIPMENT_CONFIRMED','ORDER_CANCELLED','RESERVATION_EXPIRED','RETURN_RECEIVED'},sorted(types))
    check('event bodies and tenant version identity valid',all(json.loads(body)['tenantId']==str(t) and json.loads(body)['aggregateVersion']==str(v) and hashlib.sha256(body.encode()).hexdigest()==h for t,v,body,h in sql('SELECT tenant_id,aggregate_version,body,body_hash FROM ful_outbox_event')))
    stop(failure)
    # Real broker outage: business transaction succeeds and stores NEW.
    shell('scripts/Stop-Messaging.ps1');offline=c.bind(source,'offline-existing-'+RUN)
    next_source=c.create('sale-order',{'customerId':f.customer,'accountId':f.account,'orderTime':b.NOW,'discountPercent':'0','items':[{'productId':fx['product'],'count':'1','productPrice':'2','taxPercent':'0'}]});c.approve('sale-order',next_source);offline_order=c.bind(next_source)['orderId']
    check('Broker offline business commits NEW outbox',sql('SELECT status FROM ful_outbox_event WHERE order_id=%s',(offline_order,))==(('NEW',),))
    shell('scripts/Start-Messaging.ps1')
    # mandatory return ACK must not be marked SENT.
    target=event_for(fx['order'],'RETURN_RECEIVED')[0];due_only(target)
    bad=start('unroutable',publisher=True,test=('--fulfillment.messages.routing-key=missing',));wait(lambda:event_status(target)[0]=='DEAD')
    check('unroutable confirmed publication becomes DEAD',sql('SELECT last_error,attempts FROM ful_outbox_event WHERE event_id=%s',(target,))==(('RETURN_312',3),))
    check('every unroutable delivery is failed not ACKED',sql('SELECT DISTINCT result FROM ful_outbox_delivery WHERE event_id=%s',(target,))==(('FAILED',),));stop(bad)
    replaykey='republish-'+RUN;replayed=c.replay(fx['order'],target,key=replaykey);check('manual republish preserves event identity',replayed['eventId']==target and c.replay(fx['order'],target,key=replaykey)==replayed)
    check('changed reason same key conflicts',c.replay(fx['order'],target,key=replaykey,ok=False,reason='不同恢复意图')['code']==1080000005)
    good=start('publish-recovery',publisher=True);wait(lambda:event_status(target)[0]=='SENT');check('manual broker recovery reaches SENT with total attempts retained',sql('SELECT attempts,total_attempts FROM ful_outbox_event WHERE event_id=%s',(target,))==((1,4),));stop(good)
    # Crash after confirm, before SENT; genuine exit, expiry and redelivery.
    crashfx=f.shipment('发布崩溃',('2',));E['fixtures']['publish_crash']=crashfx;crash=event_for(crashfx['order'],'SHIPMENT_CONFIRMED')[0];due_only(crash)
    cp=start('confirm-crash',publisher=True,test=('--fulfillment.test.message-crash=AFTER_CONFIRM',));wait(lambda:cp.poll() is not None)
    check('actual process exits at after-confirm window',cp.returncode==71 and log_has('confirm-crash','M5_CRASH_AFTER_CONFIRM'))
    check('confirm crash leaves IN_FLIGHT without SENT',event_status(crash)[0]=='IN_FLIGHT')
    recovery=start('lease-recovery',publisher=True);wait(lambda:event_status(crash)[0]=='SENT');check('expired publisher lease reclaimed with higher version',event_status(crash)[1]>=2 and {x[0] for x in sql('SELECT result FROM ful_outbox_delivery WHERE event_id=%s',(crash,))}=={'EXPIRED','ACKED'});stop(recovery)
    fence(c,crashfx,crash,a)
    a=start('api-again',48082);c=Client(48082).login()
    # Canonical events deliberately delivered newest-first and duplicated.
    all_bodies=[r[0] for r in sql('SELECT body FROM ful_outbox_event ORDER BY aggregate_version DESC,id DESC')];put_messages(all_bodies+all_bodies)
    normal=start('consume-normal',consumer=True)
    wait(lambda:sql("SELECT COUNT(*) FROM ful_inbox_event WHERE status='PROCESSED'")[0][0]==sql('SELECT COUNT(*) FROM ful_outbox_event')[0][0])
    wait(lambda:queue_count()==0)
    check('all events processed with one Inbox each',not sql('SELECT event_id FROM ful_inbox_event GROUP BY tenant_id,consumer_name,event_id HAVING COUNT(*)<>1'))
    check('duplicates observed without duplicate local effects',sql('SELECT SUM(duplicate_count) FROM ful_inbox_event')[0][0]>0)
    check('out of order events cannot overwrite newer read model',not sql('SELECT o.id FROM ful_order o LEFT JOIN ful_order_read_model m ON m.tenant_id=o.tenant_id AND m.order_id=o.id WHERE m.id IS NULL OR m.observed_version<>o.version'))
    check('older versions recorded as processed without applying',sql("SELECT COUNT(*) FROM ful_inbox_event WHERE status='PROCESSED' AND applied=0")[0][0]>0)
    before=facts();put_messages([b'{"broken":',all_bodies[0].replace('"payloadVersion":1','"payloadVersion":99'),all_bodies[0].replace('"tenantId":"1"','"tenantId":"999999"')]);wait(lambda:queue_count(True)>=3)
    check('malformed incompatible and forged-tenant messages quarantined',queue_count(True)>=3 and before==facts());stop(normal)
    # Consumer failure rolls back projection, then durable retry owns responsibility.
    failed=f.shipment('消费失败',('2',));E['fixtures']['consume_failure']=failed;failed_event=event_for(failed['order'],'SHIPMENT_CONFIRMED');put_messages([failed_event[1]])
    cf=start('consumer-fault',consumer=True,test=('--fulfillment.test.message-consumer-failure=true',));wait(lambda:sql('SELECT status FROM ful_inbox_event WHERE event_id=%s',(failed_event[0],))==(('DEAD',),))
    check('failed projection is rolled back before persistent retry',not sql('SELECT id FROM ful_order_read_model WHERE order_id=%s',(failed['order'],)))
    check('consumer retries bounded and Broker delivery ACKed after durable failure',sql('SELECT attempts,applied+0 FROM ful_inbox_event WHERE event_id=%s',(failed_event[0],))==((3,0),) and queue_count()==0);stop(cf)
    normal=start('consumer-recovery',consumer=True);consume_key='consume-'+RUN;c.replay(failed['order'],failed_event[0],'RETRY_CONSUME',consume_key);wait(lambda:sql('SELECT status FROM ful_inbox_event WHERE event_id=%s',(failed_event[0],))==(('PROCESSED',),))
    first=c.replay(failed['order'],failed_event[0],'RETRY_CONSUME',consume_key);check('manual consume retry response durable',first['outcome']=='CONSUME_RETRY_QUEUED')
    check('processed consume retry produces no second effect',c.replay(failed['order'],failed_event[0],'RETRY_CONSUME')['outcome']=='ALREADY_PROCESSED');stop(normal)
    # Actual JVM termination after local commit but before ACK.
    ackfx=f.shipment('确认前崩溃',('2',));E['fixtures']['ack_crash']=ackfx;ackevent=event_for(ackfx['order'],'SHIPMENT_CONFIRMED');put_messages([ackevent[1]])
    ap=start('ack-crash',consumer=True,test=('--fulfillment.test.message-crash=BEFORE_ACK',));wait(lambda:ap.poll() is not None)
    check('actual process exits after consumer commit before ACK',ap.returncode==72 and log_has('ack-crash','M5_CRASH_BEFORE_ACK'))
    check('Inbox committed before ACK crash',sql('SELECT status FROM ful_inbox_event WHERE event_id=%s',(ackevent[0],))==(('PROCESSED',),))
    projection=sql('SELECT * FROM ful_order_read_model WHERE order_id=%s',(ackfx['order'],));before=facts();normal=start('final-consumer',consumer=True)
    wait(lambda:sql('SELECT duplicate_count FROM ful_inbox_event WHERE event_id=%s',(ackevent[0],))[0][0]>=1)
    check('redelivered ACK crash leaves projection and business facts unchanged',sql('SELECT * FROM ful_order_read_model WHERE order_id=%s',(ackfx['order'],))==projection and facts()==before)
    permissions(c,f,fx,target,replaykey)
    # Rebuild can repair disposable projection at the same business version.
    before=facts();sql("UPDATE ful_order_read_model SET snapshot_json='{}' WHERE order_id=%s",(fx['order'],));E['injections'].append({'kind':'read_model_corruption','order':fx['order']})
    rebuildkey='rebuild-'+RUN;rebuilt=c.rebuild(fx['order'],rebuildkey);check('rebuild idempotent and repairs same-version projection',c.rebuild(fx['order'],rebuildkey)==rebuilt and sql('SELECT snapshot_json FROM ful_order_read_model WHERE order_id=%s',(fx['order'],))[0][0]!='{}' and facts()==before)
    old=event_for(fx['order'],'ORDER_BOUND')[1];saved=sql('SELECT * FROM ful_order_read_model WHERE order_id=%s',(fx['order'],));put_messages([old]);wait(lambda:queue_count()==0);check('old delivery after rebuild cannot regress projection',sql('SELECT * FROM ful_order_read_model WHERE order_id=%s',(fx['order'],))==saved)
    stop(normal)
    # Drain every real Outbox event with both workers enabled; direct injections did not mark SENT.
    sql("UPDATE ful_outbox_event SET next_attempt_at=UTC_TIMESTAMP(6) WHERE status IN ('NEW','RETRY_WAIT')")
    final=start('final-pipeline',publisher=True,consumer=True);wait(lambda:sql("SELECT COUNT(*) FROM ful_outbox_event WHERE status<>'SENT'")[0][0]==0,120);wait(lambda:sql("SELECT COUNT(*) FROM ful_inbox_event WHERE status='PROCESSED'")[0][0]==sql('SELECT COUNT(*) FROM ful_outbox_event')[0][0],120)
    check('final complete pipeline SENT and PROCESSED every event',not sql("SELECT o.event_id FROM ful_outbox_event o LEFT JOIN ful_inbox_event i ON i.tenant_id=o.tenant_id AND i.event_id=o.event_id WHERE o.status<>'SENT' OR i.status<>'PROCESSED' OR i.id IS NULL"))
    check('all event projections converge to business version',not sql('SELECT o.id FROM ful_order o LEFT JOIN ful_order_read_model m ON m.tenant_id=o.tenant_id AND m.order_id=o.id WHERE m.id IS NULL OR m.observed_version<>o.version'))
    check('H R and fulfillment facts remain consistent',c.api('POST','/fulfillment/reconcile/run',{'scope':'TENANT'},headers={'Idempotency-Key':uuid.uuid4().hex})['differenceCount']==0)
    E['final_counts']={t:sql('SELECT COUNT(*) FROM '+t)[0][0] for t in ['ful_outbox_event','ful_outbox_delivery','ful_inbox_event','ful_order_read_model','ful_message_action']};E['result']='passed';stop(final)
    # Restart a clean API process to verify replay/audits survive application restart.
    stop(a);a=start('restart-api',48082);c=Client(48082).login();check('manual replay key survives JVM restart',c.replay(fx['order'],target,key=replaykey)==replayed);check('rebuild key survives JVM restart',c.rebuild(fx['order'],rebuildkey)==rebuilt)

def fence(c,fixture,event,api):
    stop(api);c=None
    with db() as locks:
        with locks.cursor() as cur:
            for prefix in ['m5claim:','m5confirm:']:cur.execute('SELECT GET_LOCK(%s,0)',(prefix+DATABASE,));check('own '+prefix+' barrier',cur.fetchone()[0]==1)
        try:
            a=start('fence-a',48082,publisher=True,test=('--fulfillment.test.message-before-claim-barrier=true',));c=Client(48082).login();c.replay(fixture['order'],event)
            due_only(event);bproc=start('fence-b',publisher=True,test=('--fulfillment.test.message-confirm-barrier=true',))
            wait(lambda:log_has('fence-b','M5_BARRIER_CONFIRM'))
            old=event_status(event)[1];check('active lease rejects manual replay',c.replay(fixture['order'],event,ok=False)['code']==1080000062)
            wait(lambda:sql('SELECT lease_until<=UTC_TIMESTAMP(6) FROM ful_outbox_event WHERE event_id=%s',(event,))[0][0]==1)
            with locks.cursor() as cur:cur.execute('SELECT RELEASE_LOCK(%s)',('m5claim:'+DATABASE,))
            wait(lambda:event_status(event)[0]=='SENT' and event_status(event)[1]>old)
            current=event_status(event)
            with locks.cursor() as cur:cur.execute('SELECT RELEASE_LOCK(%s)',('m5confirm:'+DATABASE,))
            wait(lambda:sql('SELECT result FROM ful_outbox_delivery WHERE event_id=%s AND lease_version=%s',(event,old))==(('LATE',),))
            check('old publisher cannot overwrite newer lease result',event_status(event)==current)
            check('two actual JVM owners competed for event',sql('SELECT COUNT(DISTINCT lease_owner) FROM ful_outbox_delivery WHERE event_id=%s',(event,))[0][0]>=2)
            stop(a);stop(bproc)
        finally:
            with locks.cursor() as cur:cur.execute('SELECT RELEASE_ALL_LOCKS()')

def permissions(c,f,fx,event,prior_key):
    menus=[r[0] for r in sql("SELECT id FROM system_menu WHERE deleted=0 AND (permission LIKE 'erp:%%' OR permission LIKE 'fulfillment:%%' OR id=597)")]
    role=c.api('POST','/system/role/create',{'name':RUN,'code':RUN,'status':0,'sort':1})
    def grant(ids):c.api('POST','/system/permission/assign-role-menu',{'roleId':role,'menuIds':ids})
    grant(menus)
    def user(label,assigned=True):
        name=RUN+label;uid=c.api('POST','/system/user/create',{'username':name,'nickname':name,'password':'admin123'})
        if assigned:c.api('POST','/system/permission/assign-user-role',{'userId':uid,'roleIds':[role]})
        return Client(48082).login(name)
    owner=user('Owner');other=user('Other');none=user('None',False)
    owned=f.shipment('归属',('1',),client=owner);E['fixtures']['owner']=owned;ev=event_for(owned['order'],'SHIPMENT_CONFIRMED')[0]
    check('anonymous message query denied',Client(48082).events(fx['order'],False)['code']==401)
    check('no query permission denied',none.events(fx['order'],False)['code']==403)
    check('other owner cannot query known order',other.events(owned['order'],False)['code']==1080000003)
    check('other owner cannot replay known event',other.replay(owned['order'],ev,ok=False)['code']==1080000003)
    check('other owner cannot rebuild known order',other.rebuild(owned['order'],ok=False)['code']==1080000003)
    check('ordinary owner queries own event',owner.event(owned['order'],ev)['eventId']==ev)
    key='owner-replay-'+RUN;owner.replay(owned['order'],ev,key=key)
    grant([m for m in menus if m!=50017]);check('revoked replay permission denies old successful key',owner.replay(owned['order'],ev,key=key,ok=False)['code']==403);grant(menus)
    grant([m for m in menus if m!=50018]);check('rebuild requires independent permission',owner.rebuild(owned['order'],ok=False)['code']==403);grant(menus)
    check('message page size bounded',c.events(fx['order'],False,pageSize=51)['code']==400)
    check('known event from another order hidden',c.event(owned['order'],event,False)['code']==1080000061)
    check('replay requires idempotency header',c.api('POST','/fulfillment/message/replay',{'orderId':owned['order'],'eventId':ev,'action':'REPUBLISH','reason':'测试'},ok=False)['code']==400)
    package=c.api('POST','/system/tenant-package/create',{'name':RUN,'status':0,'menuIds':menus})
    tid=c.api('POST','/system/tenant/create',{'name':RUN+'租户','contactName':'M5','status':0,'packageId':package,'expireTime':'2035-12-31T23:59:59','accountCount':10,'username':RUN+'Tenant','password':'admin123','websites':[]})
    foreign=Client(48082,tid).login(RUN+'Tenant')
    check('foreign tenant known order denied',foreign.events(fx['order'],False)['code']==1080000003)
    ff=b.Fixture(foreign,'Foreign');ffx=ff.shipment('租户隔离',('1',));E['fixtures']['foreign']=ffx
    fev=event_for(ffx['order'],'SHIPMENT_CONFIRMED');put_messages([fev[1]]);wait(lambda:sql('SELECT status FROM ful_inbox_event WHERE event_id=%s',(fev[0],))==(('PROCESSED',),))
    check('trusted foreign event applies only its own tenant',sql('SELECT tenant_id FROM ful_order_read_model WHERE order_id=%s',(ffx['order'],))==((tid,),))
    check('tenant one cannot get foreign message',c.event(ffx['order'],fev[0],False)['code']==1080000003)

if __name__=='__main__':
    try:main()
    except Exception as error:E['result']='failed';E['error']=str(error);raise
    finally:
        for p,out in OWNED:stop(p);out.close()
        E['all_owned_processes_stopped']=all(p.poll() is not None for p,_ in OWNED)
        prefix='M5-' if E.get('result')=='passed' else 'M5-failed-'+DATABASE+'-'
        for path in (ROOT/'.local').glob('m5-*-out.log'):shutil.copyfile(path,ROOT/'../学习资料/10-验收证据'/(prefix+path.name))
        target='M5-acceptance.json' if E.get('result')=='passed' else 'M5-failed-'+DATABASE+'.json'
        (ROOT/'../学习资料/10-验收证据'/target).write_text(json.dumps(E,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
        print('M5 acceptance',E.get('result'),len(E['checks']),'checks',DATABASE,flush=True)
