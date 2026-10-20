"""M4.1 isolated MySQL/Redis-DB4, real Java processes and HTTP acceptance.
Creates fixtures via APIs. SQL writes ONLY alter labelled fixture deadlines to stage
lock races/backlogs, never H/R/quantity facts. No business data cleanup.
PowerShell path must be supplied as M0_PWSH when pwsh isn't on PATH.
"""
import concurrent.futures, hashlib, json, os, shutil, subprocess, time, uuid
from datetime import datetime, timezone
from decimal import Decimal as D
from pathlib import Path
from m1_acceptance import ROOT, db, sql
from m3_acceptance import M3Client

DATABASE=os.getenv('M4_DATABASE','fulfillment_m4_expiry_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
os.environ['DB_NAME']=DATABASE
RUN='M4E'+uuid.uuid4().hex[:8]
NOW=datetime.now().isoformat(timespec='seconds')
E={'run_at':datetime.now(timezone.utc).isoformat(),'database':DATABASE,'redis_database':4,
   'checks':[],'processes':[],'deadline_injections':[],'ids':{},'commands':[]}
PROCESSES=[]
JAR=ROOT/'.local/m4-expiry-run.jar'
POOL=concurrent.futures.ThreadPoolExecutor(max_workers=8)

def check(name,ok,detail=None):
    E['checks'].append({'name':name,'passed':bool(ok),'detail':detail})
    if not ok: raise AssertionError(name+': '+str(detail))

def wait_for(predicate,timeout=20):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        value=predicate()
        if value:return value
        time.sleep(.2)
    raise AssertionError('Timed out waiting for condition')

def shell(script,*arguments):
    executable=os.environ.get('M0_PWSH') or shutil.which('pwsh')
    if not executable:raise RuntimeError('Set M0_PWSH to the current PowerShell executable')
    log=ROOT/'.local'/('m4-expiry-'+Path(script).stem+'-'+str(len(E['commands']))+'.log')
    with log.open('wb') as out:
        result=subprocess.run([executable,'-NoProfile','-File',str(ROOT/script),*arguments],cwd=ROOT,stdout=out,stderr=subprocess.STDOUT,timeout=180)
    E['commands'].append({'script':script,'arguments':arguments,'exit_code':result.returncode,'log':str(log.relative_to(ROOT))})
    check('command '+Path(script).stem+' '+str(arguments),result.returncode==0,str(log))

def start(port,name,enabled=True,fault=False):
    env=os.environ.copy();env['APP_PORT']=str(port)
    log=ROOT/'.local'/('m4-expiry-'+name+'-out.log')
    out=log.open('ab' if any(p['name']==name for p in E['processes']) else 'wb')
    args=[shutil.which('java'),'-Xms128m','-Xmx768m','-Dfile.encoding=UTF-8','-Duser.timezone=Asia/Shanghai','-jar',str(JAR),
          '--spring.profiles.active=fulfillment'+(',fulfillment-expiry-fault-test' if fault else ''),
          '--spring.data.redis.database=4','--fulfillment.expiry.enabled='+str(enabled).lower(),
          '--fulfillment.expiry.delay-ms=1000','--fulfillment.expiry.initial-delay-ms=1000',
          '--fulfillment.expiry.batch-size=2','--fulfillment.expiry.max-batches=1',
          '--logging.file.name=../.local/m4-expiry-'+name+'-app.log']
    proc=subprocess.Popen(args,cwd=ROOT/'backend',env=env,stdout=out,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    PROCESSES.append((proc,out));E['processes'].append({'port':port,'pid':proc.pid,'name':name,'expiry':enabled,'fault':fault})
    def ready():
        if proc.poll() is not None:raise AssertionError('Process exited '+name+'; see '+str(log))
        try:return M3Client(port).login()
        except Exception:return False
    wait_for(ready,65)
    return proc

def stop(proc):
    if proc.poll() is None:
        proc.terminate()
        try:proc.wait(25)
        except subprocess.TimeoutExpired:proc.kill();proc.wait(10)

def deadline(reservations,seconds=-1):
    # Explicit, test-only deadline injection, preserving all quantity facts.
    for reservation in reservations:
        sql('UPDATE ful_reservation SET expire_at=DATE_ADD(UTC_TIMESTAMP(6),INTERVAL %s MICROSECOND) WHERE id=%s',(int(seconds*1_000_000),reservation))
        E['deadline_injections'].append({'reservation':reservation,'seconds_from_sql_now':seconds})

def balance(p,w):return sql('SELECT `count`,ful_reserved_count FROM erp_stock WHERE product_id=%s AND warehouse_id=%s',(p,w))[0]
def qty(order):return sql('SELECT open_qty,reserved_qty,shipped_qty,cancelled_qty FROM ful_order_item WHERE order_id=%s ORDER BY id',(order,))
def closed(rs):return sql('SELECT held_qty FROM ful_reservation WHERE id=%s',(rs,))[0][0]==0
def lock_source(source):
    connection=db();connection.begin();connection.cursor().execute('SELECT id FROM erp_sale_order WHERE id=%s FOR UPDATE',(source,));return connection
def text_log(name):return (ROOT/'.local'/('m4-expiry-'+name+'-out.log')).read_text(encoding='utf-8',errors='replace')

class Fixture:
    def __init__(self,client,label):
        self.client=client;self.products=[];self.label=RUN+label
        self.unit=client.create('product-unit',{'name':self.label+'件','status':0})
        self.category=client.create('product-category',{'name':self.label,'code':self.label,'parentId':0,'sort':1,'status':0})
        self.customer=client.create('customer',{'name':self.label+'客户','status':0,'sort':1})
        self.supplier=client.create('supplier',{'name':self.label+'供应商','status':0,'sort':1})
        self.account=client.create('account',{'name':self.label+'账户','no':self.label,'status':0,'sort':1})
        self.w=client.create('warehouse',{'name':self.label+'仓','sort':1,'status':0,'warehousePrice':'0','truckagePrice':'0'})
    def order(self,label,q='3',h='5',hold=900):
        p=self.client.create('product',{'name':self.label+label,'barCode':self.label+label,'categoryId':self.category,'unitId':self.unit,'status':0,'salePrice':'0','purchasePrice':'0'})
        self.products.append(p)
        doc=self.client.create('stock-in',{'supplierId':self.supplier,'inTime':NOW,'items':[{'productId':p,'warehouseId':self.w,'productPrice':'0','count':h}]});self.client.approve('stock-in',doc)
        source=self.client.create('sale-order',{'customerId':self.customer,'accountId':self.account,'orderTime':NOW,'discountPercent':'0','items':[{'productId':p,'count':q,'productPrice':'0','taxPercent':'0'}]})
        self.client.approve('sale-order',source);order=self.client.bind(source)['orderId']
        item=self.client.api('GET','/fulfillment/order/get',params={'id':order})['items'][0]['id']
        result=self.client.api('POST','/fulfillment/order/allocate',{'orderId':order,'warehouseIds':[str(self.w)],'strategy':'PRIORITY_SPLIT','holdSeconds':hold},headers={'Idempotency-Key':uuid.uuid4().hex})
        r=result['reservations'][0]
        E['ids'][self.label+label]={'source':source,'order':order,'item':item,'product':p,'warehouse':self.w,'reservation':r['id'],'expireAt':r['expireAt']}
        return p,source,order,item,r

def invariant():
    bad=sql('SELECT s.id FROM erp_stock s WHERE s.`count`<s.ful_reserved_count OR s.ful_reserved_count<0 OR s.ful_reserved_count<>(SELECT COALESCE(SUM(r.held_qty),0) FROM ful_reservation r WHERE r.tenant_id=s.tenant_id AND r.product_id=s.product_id AND r.warehouse_id=s.warehouse_id) OR s.ful_reserved_count<>(SELECT COALESCE(SUM(l.held_delta),0) FROM ful_stock_ledger l WHERE l.tenant_id=s.tenant_id AND l.product_id=s.product_id AND l.warehouse_id=s.warehouse_id) OR s.`count`<>(SELECT COALESCE(SUM(l.`count`),0) FROM erp_stock_record l WHERE l.tenant_id=s.tenant_id AND l.product_id=s.product_id AND l.warehouse_id=s.warehouse_id)')
    check('all tenants H R reservations and ledgers agree',not bad,bad)
    bad=sql('SELECT i.id FROM ful_order_item i WHERE i.reserved_qty<>(SELECT COALESCE(SUM(r.held_qty),0) FROM ful_reservation r WHERE r.tenant_id=i.tenant_id AND r.order_item_id=i.id) OR i.shipped_qty<>(SELECT COALESCE(SUM(s.quantity),0) FROM ful_shipment_item s WHERE s.tenant_id=i.tenant_id AND s.order_item_id=i.id) OR i.cancelled_qty<>(SELECT COALESCE(SUM(c.quantity),0) FROM ful_cancellation c WHERE c.tenant_id=i.tenant_id AND c.order_item_id=i.id)')
    check('all order aggregates agree with business facts',not bad,bad)
    bad=sql("SELECT r.id FROM ful_reservation r WHERE r.allocated_qty<>r.held_qty+r.consumed_qty+r.released_qty OR r.active_flag<>(r.held_qty>0)")
    check('reservation identities and active flags intact',not bad,bad)
    bad=sql("SELECT reservation_id FROM ful_stock_ledger WHERE event_type='EXPIRE' GROUP BY tenant_id,reservation_id HAVING COUNT(*)>1")
    check('no reservation has duplicate expiry ledger effect',not bad,bad)
    check('system audit uses actor0',not sql("SELECT id FROM ful_stock_ledger WHERE event_type='EXPIRE' AND (actor_id<>0 OR creator<>'0' OR updater<>'0')"))
    check('only completed durable expiry commands',not sql("SELECT id FROM ful_command_record WHERE command_type='EXPIRE' AND (actor_id<>0 OR response_json IS NULL OR response_code<>0)"))

def main():
    check('test ports initially free',all(__import__('socket').socket().connect_ex(('127.0.0.1',p))!=0 for p in [48082,48083]))
    shell('scripts/Initialize-Database.ps1','-Database',DATABASE)
    for action in ['baseline','migrate','validate']:shell('scripts/Migrate-Database.ps1','-Action',action,'-Database',DATABASE)
    shutil.copyfile(ROOT/'backend/yudao-server/target/yudao-server.jar',JAR)
    a=start(48082,'a-disabled',False)
    # Fresh install also exercises M1 source freezing, auth, tenant isolation and binding.
    env=os.environ.copy();env.update(API_BASE='http://127.0.0.1:48082',M1_EVIDENCE='M4.1-clean-binding.json')
    log=ROOT/'.local/m4-expiry-m1-regression.log'
    with log.open('wb') as out:result=subprocess.run([__import__('sys').executable,str(ROOT/'tests/m1_acceptance.py')],env=env,stdout=out,stderr=subprocess.STDOUT,timeout=150)
    check('fresh database M1 regression',result.returncode==0,str(log))
    check('history remains immutable 0 through 3',tuple(x[0] for x in sql('SELECT version FROM ful_flyway_schema_history ORDER BY installed_rank'))==('0','1','2','3'))
    admin=M3Client(48082).login();f=Fixture(admin,'A')
    p,source,order,item,r=f.order('故障','3.123456','5')
    before=(balance(p,f.w),qty(order),sql('SELECT allocated_qty,held_qty,consumed_qty,released_qty,active_flag,version FROM ful_reservation WHERE id=%s',(r['id'],)),sql('SELECT version,status FROM ful_order WHERE id=%s',(order,)))
    b=start(48083,'fault',True,True);deadline([r['id']])
    wait_for(lambda:'M4_TEST_FAILURE_AFTER_EXPIRY_WRITES' in text_log('fault'),20)
    # Wait for at least a second attempt, proving failures remain eligible.
    wait_for(lambda:text_log('fault').count('M4_TEST_FAILURE_AFTER_EXPIRY_WRITES')>=2,10)
    check('fault after all writes rolls back all quantity and version facts',before==(balance(p,f.w),qty(order),sql('SELECT allocated_qty,held_qty,consumed_qty,released_qty,active_flag,version FROM ful_reservation WHERE id=%s',(r['id'],)),sql('SELECT version,status FROM ful_order WHERE id=%s',(order,))))
    check('failed expiry leaves no ledger or command',not sql("SELECT id FROM ful_stock_ledger WHERE reservation_id=%s AND event_type='EXPIRE'",(r['id'],)) and not sql("SELECT id FROM ful_command_record WHERE command_type='EXPIRE' AND idempotency_key=%s",('reservation:'+r['id'],)))
    check('fault does not create physical ledger',sql('SELECT COUNT(*) FROM erp_stock_record WHERE product_id=%s',(p,))[0][0]==1)
    stop(b);b=start(48083,'b',True)
    wait_for(lambda:closed(r['id']))
    check('healthy restart retries rolled back same system key',balance(p,f.w)==(D(5),D(0)) and qty(order)==((D('3.123456'),D(0),D(0),D(0)),))
    check('one completed expiry command after recovery',sql("SELECT COUNT(*) FROM ful_command_record WHERE command_type='EXPIRE' AND idempotency_key=%s",('reservation:'+r['id'],))[0][0]==1)
    stop(a);a=start(48082,'a',True);admin=M3Client(48082).login();f.client=admin
    check('two active workers are distinct real JVMs',a.pid!=b.pid and a.poll() is None and b.poll() is None)

    # Natural 60-second deadline; no clock injection on this reservation.
    np,ns,no,ni,nr=f.order('自然到期','3.123456','5',60);natural_time=datetime.fromisoformat(nr['expireAt']).timestamp()
    ship_key='natural-ship-'+RUN;shipped=admin.ship(no,f.w,[(nr['id'],'1.123456')],ship_key)
    admin.release(no,[(nr['id'],'0.111111')])
    check('partial ship and manual release leave precise held',balance(np,f.w)==(D('3.876544'),D('1.888889')))

    # Both scanners must read the same candidate while its source is locked.
    dp,ds,do,di,dr=f.order('重复扫描');lock=lock_source(ds)
    try:deadline([dr['id']]);time.sleep(2.1)
    finally:lock.rollback();lock.close()
    wait_for(lambda:closed(dr['id']))
    wait_for(lambda:all('reservation='+dr['id']+' outcome=EXPIRED' in text_log(name) for name in ['a','b']))
    check('both JVMs observe the saved result but release once',sql("SELECT COUNT(*) FROM ful_stock_ledger WHERE reservation_id=%s AND event_type='EXPIRE'",(dr['id'],))[0][0]==1 and balance(dp,f.w)==(D(5),D(0)))

    # First due row is unprocessable; bounded cursor must reach later pages before unlock.
    backlog=[f.order('积压'+str(i)) for i in range(7)];first=backlog[0];lock=lock_source(first[1])
    try:
        deadline([x[4]['id'] for x in backlog])
        wait_for(lambda:all(closed(x[4]['id']) for x in backlog[1:]),17)
        check('failed first row cannot starve subsequent bounded pages',not closed(first[4]['id']))
        check('real database lock retry was exercised',any('Retry entire database command after lock failure' in text_log(name) for name in ['a','b']))
    finally:lock.rollback();lock.close()
    wait_for(lambda:closed(first[4]['id']))
    check('failed first row revisited after scan wraps',closed(first[4]['id']))

    # Ship acquired order and reservation before deadline, then waited for stock past it.
    sp,ss,so,si,sr=f.order('发货等锁');lock=db();lock.begin();lock.cursor().execute('SELECT id FROM erp_stock WHERE product_id=%s AND warehouse_id=%s FOR UPDATE',(sp,f.w))
    try:
        deadline([sr['id']],1.2)
        future=POOL.submit(lambda:M3Client(48082).login().ship(so,f.w,[(sr['id'],'1')],ok=False))
        time.sleep(2.1)
    finally:lock.rollback();lock.close()
    response=future.result(35)
    check('ship rechecks clock after stock lock wait',response['code']==1080000020,response)
    wait_for(lambda:closed(sr['id']))
    check('expired ship creates no ERP out and changes no physical',balance(sp,f.w)==(D(5),D(0)) and not sql('SELECT id FROM erp_sale_out WHERE order_id=%s',(ss,)))

    # A legal pre-deadline ship consumes its reservation; expiry never reopens shipped quantity.
    wp,ws,wo,wi,wr=f.order('先发完','2.000001','5');deadline([wr['id']],4)
    success=admin.ship(wo,f.w,[(wr['id'],'2.000001')]);time.sleep(5)
    check('pre-deadline shipment wins and stays fulfilled',balance(wp,f.w)==(D('2.999999'),D(0)) and qty(wo)==((D(0),D(0),D('2.000001'),D(0)),))
    check('consumed rows never enter expiry scan',not sql("SELECT id FROM ful_stock_ledger WHERE reservation_id=%s AND event_type='EXPIRE'",(wr['id'],)))

    # Cancel/release and expiry share the same source/order serialization.
    cp,cs,co,ci,cr=f.order('取消竞争');deadline([cr['id']])
    cancel=POOL.submit(lambda:M3Client(48082).login().cancel(co,[(ci,'3')]))
    cancel.result(40);wait_for(lambda:closed(cr['id']))
    check('cancel versus expiry closes quantity exactly once',qty(co)==((D(0),D(0),D(0),D(3)),) and balance(cp,f.w)==(D(5),D(0)))
    rp,rs,ro,ri,rr=f.order('释放竞争');deadline([rr['id']])
    release=POOL.submit(lambda:M3Client(48083).login().release(ro,[(rr['id'],'3')],ok=False)).result(40)
    check('release versus expiry has only legal outcomes',release['code'] in [0,1080000012],release)
    wait_for(lambda:closed(rr['id']))
    check('release race never duplicates released quantity',sql('SELECT released_qty FROM ful_reservation WHERE id=%s',(rr['id'],))[0][0]==3 and balance(rp,f.w)==(D(5),D(0)))

    # Real second tenant, processed interleaved with tenant1 by the same scheduler threads.
    menu=[x[0] for x in sql("SELECT id FROM system_menu WHERE deleted=0 AND (permission LIKE 'erp:%%' OR permission LIKE 'fulfillment:%%' OR id=597)")]
    package=admin.api('POST','/system/tenant-package/create',{'name':RUN+'套餐','status':0,'menuIds':menu})
    tenant=admin.api('POST','/system/tenant/create',{'name':RUN+'租户','contactName':'M4.1','status':0,'packageId':package,'expireTime':'2035-12-31T23:59:59','accountCount':10,'username':RUN+'Tenant','password':'admin123','websites':[]})
    other=M3Client(48082,tenant).login(RUN+'Tenant');of=Fixture(other,'B')
    op,osource,oo,oi,ors=of.order('租户到期','1.000001','4');tp,ts,to,ti,tr=f.order('租户交错','2.000001','5')
    deadline([ors['id'],tr['id']]);wait_for(lambda:closed(ors['id']) and closed(tr['id']))
    check('interleaved tenants release their own exact quantity',balance(op,of.w)==(D(4),D(0)) and balance(tp,f.w)==(D(5),D(0)))
    check('system commands retain each candidate tenant',set(sql("SELECT tenant_id,actor_id FROM ful_command_record WHERE command_type='EXPIRE' AND idempotency_key IN (%s,%s)",('reservation:'+ors['id'],'reservation:'+tr['id'])))=={(tenant,0),(1,0)})
    check('expiry does not change HTTP ownership or tenant authorization',admin.api('GET','/fulfillment/order/get',params={'id':oo},ok=False)['code']==1080000003 and other.api('GET','/fulfillment/order/get',params={'id':to},ok=False)['code']==1080000003)

    # Wait out the original real clock; the scheduler alone must perform the business change.
    wait_for(lambda:time.time()>natural_time and closed(nr['id']),max(20,natural_time-time.time()+15))
    check('natural expiry releases only remaining held',qty(no)==((D(2),D(0),D('1.123456'),D(0)),) and balance(np,f.w)==(D('3.876544'),D(0)))
    check('natural expiry records exact delta and no physical effect',sql("SELECT held_delta,actor_id FROM ful_stock_ledger WHERE reservation_id=%s AND event_type='EXPIRE'",(nr['id'],))==((D('-1.888889'),0),) and sql('SELECT COUNT(*) FROM erp_stock_record WHERE product_id=%s',(np,))[0][0]==2)
    check('successful ship replay remains valid after later expiry',admin.ship(no,f.w,[(nr['id'],'1.123456')],ship_key)==shipped)
    new=admin.allocate(no,[f.w])
    check('reallocation creates new identity for reopened quantity',new['reservations'][0]['id']!=nr['id'] and new['reservations'][0]['heldQty']=='2.000000')
    check('historical expiry command cannot consume new reservation',balance(np,f.w)==(D('3.876544'),D(2)))

    # App restart with a persisted, overdue reservation and no in-memory scan progress.
    zp,zs,zo,zi,zr=f.order('重启补扫','1.234567','5');stop(a);stop(b);deadline([zr['id']])
    persisted=sql('SELECT held_qty,released_qty FROM ful_reservation WHERE id=%s',(zr['id'],))
    time.sleep(1);check('stopped workers leave durable held for recovery',persisted==((D('1.234567'),D(0)),))
    a=start(48082,'a-restart',True);b=start(48083,'b-restart',True);wait_for(lambda:closed(zr['id']))
    check('new JVMs recover overdue held without saved scan cursor',balance(zp,f.w)==(D(5),D(0)) and qty(zo)==((D('1.234567'),D(0),D(0),D(0)),))
    time.sleep(3)
    check('restart repeated scans have one durable effect',sql("SELECT COUNT(*) FROM ful_stock_ledger WHERE reservation_id=%s AND event_type='EXPIRE'",(zr['id'],))[0][0]==1 and sql("SELECT COUNT(*) FROM ful_command_record WHERE command_type='EXPIRE' AND idempotency_key=%s",('reservation:'+zr['id'],))[0][0]==1)
    invariant()
    E['natural_expiry']={'reservation':nr['id'],'deadline':nr['expireAt'],'checked_at':datetime.now(timezone.utc).isoformat(),'no_deadline_injection':not any(x['reservation']==nr['id'] for x in E['deadline_injections'])}
    E['result']='passed'

if __name__=='__main__':
    try:main()
    except Exception as exc:E['result']='failed';E['error']=str(exc);raise
    finally:
        for proc,out in PROCESSES:
            stop(proc);out.close()
        POOL.shutdown(wait=True)
        E['all_owned_processes_stopped']=all(proc.poll() is not None for proc,_ in PROCESSES)
        for path in sorted((ROOT/'.local').glob('m4-expiry-*-out.log')):
            dest=ROOT/'../学习资料/10-验收证据'/('M4.1-'+path.name)
            shutil.copyfile(path,dest)
        (ROOT/'../学习资料/10-验收证据/M4.1-expiry-acceptance.json').write_text(json.dumps(E,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
        print('M4.1 expiry',E.get('result'),len(E['checks']),'checks',DATABASE,flush=True)
