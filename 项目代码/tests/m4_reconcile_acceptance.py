"""M4.3 new independent database, real HTTP/JVM/MVCC and recorded corruption.
Only this labelled test schema is deliberately changed; each probe restores exact
rows in finally. No main business facts are changed and no report repairs them.
"""
import concurrent.futures,json,os,shutil,socket,subprocess,time,uuid
from datetime import datetime,timezone
from decimal import Decimal as D
DATABASE='fulfillment_m4_reconcile_'+datetime.now().strftime('%Y%m%d_%H%M%S')
os.environ['DB_NAME']=DATABASE;os.environ['M4_RETURN_DATABASE']=DATABASE
import m4_return_acceptance as b
from m1_acceptance import ROOT,sql,db
from m3_acceptance import M3Client
E={'run_at':datetime.now(timezone.utc).isoformat(),'database':DATABASE,'checks':[],'processes':[],'injections':[],'commands':[]}
OWNED=[];JAR=ROOT/'.local/m4-reconcile-run.jar';RUN='M4C'+uuid.uuid4().hex[:8]
TABLES=['erp_stock','erp_stock_record','ful_order','ful_order_item','ful_reservation','ful_stock_ledger','ful_shipment','ful_shipment_item','ful_cancellation','ful_return','ful_return_item','erp_sale_order','erp_sale_order_items','erp_sale_out','erp_sale_out_items','erp_sale_return','erp_sale_return_items']
def check(name,ok,detail=None):
    E['checks'].append({'name':name,'passed':bool(ok),'detail':detail});print(('PASS ' if ok else 'FAIL ')+name,flush=True)
    if not ok:raise AssertionError(name+': '+str(detail))
b.check=check
class Client(b.Client):
    def scan(self,key=None,ok=True,extra=None):return self.api('POST','/fulfillment/reconcile/run',{'scope':'TENANT',**(extra or {})},headers={'Idempotency-Key':key or uuid.uuid4().hex},ok=ok)
    def findings(self,run,**params):return self.api('GET','/fulfillment/reconcile/items',params={'runId':run,'pageSize':100,**params})
    def review(self,item,note,key=None,ok=True):return self.api('POST','/fulfillment/reconcile/review',{'itemId':item,'note':note},headers={'Idempotency-Key':key or uuid.uuid4().hex},ok=ok)
def start(label,port=48083,*options):
    env=os.environ.copy();env['APP_PORT']=str(port)
    out=(ROOT/'.local'/('m4-reconcile-'+label+'-out.log')).open('wb')
    args=[shutil.which('java'),'-Xms128m','-Xmx768m','-Dfile.encoding=UTF-8','-Duser.timezone=Asia/Shanghai','-jar',str(JAR),'--spring.profiles.active=fulfillment'+(',fulfillment-reconcile-test' if options else ''),'--spring.data.redis.database=6','--logging.file.name=../.local/m4-reconcile-'+label+'-app.log',*options]
    p=subprocess.Popen(args,cwd=ROOT/'backend',env=env,stdout=out,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    OWNED.append((p,out));E['processes'].append({'label':label,'pid':p.pid,'port':port,'options':options})
    def ready():
        if p.poll() is not None:raise AssertionError('JVM exited '+label)
        try:return Client(port).login()
        except Exception:return False
    b.wait_for(ready);return p
def shell(file,*args):
    path=ROOT/'.local'/('m4-reconcile-setup-'+str(len(E['commands']))+'.log')
    with path.open('wb') as out:r=subprocess.run([os.environ['M0_PWSH'],'-NoProfile','-File',str(ROOT/file),*args],stdout=out,stderr=subprocess.STDOUT,timeout=180)
    E['commands'].append({'script':file,'args':args,'exit_code':r.returncode,'log':str(path.relative_to(ROOT))});check('setup '+str(args),r.returncode==0)
def facts():return {t:sql('SELECT * FROM '+t+' ORDER BY id') for t in TABLES}
def report_counts():return sql('SELECT (SELECT COUNT(*) FROM ful_reconcile_run),(SELECT COUNT(*) FROM ful_reconcile_item),(SELECT COUNT(*) FROM ful_reconcile_review),(SELECT COUNT(*) FROM ful_command_record)')
def restored_probe(c,table,ident,column,value,rule):
    with db() as con:
        with con.cursor() as cur:
            cur.execute('SELECT * FROM '+table+' WHERE id=%s',(ident,));columns=[x[0] for x in cur.description];saved=cur.fetchone()
    before=saved[columns.index(column.strip('`'))]
    try:
        sql('UPDATE '+table+' SET '+column+'=%s WHERE id=%s',(value,ident));dirty=facts();r=c.scan();f=c.findings(r['id'])['list']
        check('detect injected '+rule,any(x['ruleCode']==rule for x in f),f)
        check('report does not repair '+rule,facts()==dirty)
        E['injections'].append({'table':table,'id':ident,'column':column,'before':str(before),'injected':str(value),'rule':rule,'report':r['id'],'findings':f})
        return r,f
    finally:sql('UPDATE '+table+' SET '+','.join('`'+x+'`=%s' for x in columns)+' WHERE id=%s',(*saved,ident))
def main():
    for port in [48082,48083]:
        with socket.socket() as s:check('test port free '+str(port),s.connect_ex(('127.0.0.1',port))!=0)
    shell('scripts/Initialize-Database.ps1','-Database',DATABASE)
    for action in ['baseline','migrate','validate']:shell('scripts/Migrate-Database.ps1','-Action',action,'-Database',DATABASE)
    shutil.copyfile(ROOT/'backend/yudao-server/target/yudao-server.jar',JAR)
    a=start('a',48082);c=Client(48082).login();f=b.Fixture(c,'Reconcile')
    fx=f.shipment('闭环',('6.000001',),ordered='10.000001');E['fixture']=fx
    req=c.create_return(fx['order'],fx['shipment'],[(fx['lines'][0]['id'],'2.000001')]);c.receive(fx['order'],req['id'])
    pending=c.create_return(fx['order'],fx['shipment'],[(fx['lines'][0]['id'],'1')]);c.reject(fx['order'],pending['id'])
    before=facts();key='clean-'+RUN;clean=c.scan(key);E['clean']=clean
    check('healthy completed shipment return cancel snapshot is clean',clean['differenceCount']==0,clean)
    check('17 table counts match actual tenant rows',clean['tableCounts']=={t:sql('SELECT COUNT(*) FROM '+t+' WHERE tenant_id=1')[0][0] for t in TABLES})
    check('scan does not modify any business row',before==facts())
    check('run replay is byte-equivalent semantic response',c.scan(key)==clean)
    check('single persisted run per key',sql("SELECT COUNT(*) FROM ful_command_record WHERE command_type='RECONCILE' AND idempotency_key=%s",(key,))[0][0]==1)
    check('get reproduces persisted report',c.api('GET','/fulfillment/reconcile/get',params={'id':clean['id']})==clean)
    stock=sql('SELECT id FROM erp_stock WHERE product_id=%s AND warehouse_id=%s',(fx['product'],fx['warehouse']))[0][0]
    restored_probe(c,'erp_stock',stock,'`count`',D('17.000001'),'STOCK_H_LEDGER')
    r,findings=restored_probe(c,'erp_stock',stock,'ful_reserved_count',D('1'),'STOCK_R_HELD');E['dirty_report']=r
    ledger=sql('SELECT id,held_delta FROM ful_stock_ledger ORDER BY id LIMIT 1')[0]
    restored_probe(c,'ful_stock_ledger',ledger[0],'held_delta',ledger[1]+D('.000001'),'RESERVATION_LEDGER')
    restored_probe(c,'ful_stock_ledger',ledger[0],'reserved_after',D(0),'STOCK_R_RUNNING')
    oi=sql('SELECT id FROM ful_order_item WHERE order_id=%s',(fx['order'],))[0][0]
    restored_probe(c,'ful_order_item',oi,'returned_qty',D(0),'ORDER_RETURNED')
    source=sql('SELECT id,out_count FROM erp_sale_order_items WHERE order_id=%s',(fx['source'],))[0]
    restored_probe(c,'erp_sale_order_items',source[0],'out_count',source[1]+1,'SOURCE_OUT_COUNT')
    erp=sql('SELECT erp_sale_out_item_id FROM ful_shipment_item WHERE shipment_id=%s',(fx['shipment'],))[0][0]
    restored_probe(c,'erp_sale_out_items',erp,'`count`',D('6.000002'),'SHIPMENT_ERP_ITEM')
    physical=sql('SELECT erp_stock_record_id FROM ful_return_item WHERE return_id=%s',(req['id'],))[0][0]
    restored_probe(c,'erp_stock_record',physical,'biz_item_id',999999,'RETURN_PHYSICAL')
    restored_probe(c,'erp_stock_record',physical,'total_count',D(0),'STOCK_H_RUNNING')
    # DELETE in isolated test schema only, then exact row restoration (including audit).
    with db() as con:
        with con.cursor() as cur:
            cur.execute('SELECT * FROM erp_stock WHERE id=%s',(stock,));columns=[x[0] for x in cur.description];saved=cur.fetchone()
    try:
        sql('DELETE FROM erp_stock WHERE id=%s',(stock,));dirty=facts();missing=c.scan();check('missing stock row found from ledger and reservation union',any(x['ruleCode']=='STOCK_MISSING' for x in c.findings(missing['id'])['list']));check('missing row is not recreated by audit',dirty==facts())
        E['injections'].append({'table':'erp_stock','id':stock,'operation':'DELETE','rule':'STOCK_MISSING','report':missing['id']})
    finally:sql('INSERT INTO erp_stock('+','.join('`'+x+'`' for x in columns)+') VALUES('+','.join(['%s']*len(columns))+')',saved)
    check('all probes restored exact business rows',facts()==before)
    item=findings[0]['id'];reviewkey='review-'+RUN;review=c.review(item,'已核实为独立测试注入，保留报告原始差异',reviewkey);E['review']=review
    check('review same key creates one trail',c.review(item,'已核实为独立测试注入，保留报告原始差异',reviewkey)==review and sql('SELECT COUNT(*) FROM ful_reconcile_review WHERE item_id=%s',(item,))[0][0]==1)
    check('review key different note conflicts',c.review(item,'不同说明',reviewkey,False)['code']==1080000005)
    check('acknowledged filter retains original evidence',c.findings(r['id'],resolutionStatus='ACKNOWLEDGED')['list'][0]['actualValue']==findings[0]['actualValue'])
    check('review is not inventory repair',facts()==before)
    check('new scan clean while old report stays dirty',c.scan()['differenceCount']==0 and c.api('GET','/fulfillment/reconcile/get',params={'id':r['id']})['differenceCount']>0)
    check('history pagination bounded',c.api('GET','/fulfillment/reconcile/page',params={'pageSize':101},ok=False)['code']==400)
    check('item pagination bounded',c.api('GET','/fulfillment/reconcile/items',params={'runId':r['id'],'pageSize':101},ok=False)['code']==400)
    check('invalid filter rejected',c.api('GET','/fulfillment/reconcile/items',params={'runId':r['id'],'ruleCode':"x' OR 1=1"},ok=False)['code']==400)
    check('run requires idempotency key',c.api('POST','/fulfillment/reconcile/run',{'scope':'TENANT'},ok=False)['code']==400)
    check('blank note rejected',c.review(item,'   ',ok=False)['code']==400)
    permissions(c,clean,r,item,key)
    second=start('b',48083);parallelkey='parallel-'+RUN
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        results=list(pool.map(lambda n:Client(48082 if n%2 else 48083).login().scan(parallelkey),range(6)))
    check('six same-key two JVM scans persist one report',len({x['id'] for x in results})==1 and sql("SELECT COUNT(*) FROM ful_command_record WHERE command_type='RECONCILE' AND idempotency_key=%s",(parallelkey,))[0][0]==1)
    b.stop(second)
    fault=start('fault',48083,'--fulfillment.test.reconcile-fail=true');fc=Client(48083).login();counts=report_counts();failurekey='failure-'+RUN
    check('after-report fault returns failure',fc.scan(failurekey,False)['code']!=0)
    check('report findings and command all rolled back',report_counts()==counts)
    check('fault did not change business facts',before==facts())
    b.stop(fault);recovered=c.scan(failurekey);check('healthy same-key retry creates complete report',recovered['differenceCount']==0)
    limited=start('limit',48083,'--fulfillment.reconcile.row-limit=1');lc=Client(48083).login();counts=report_counts();limitkey='limit-'+RUN
    check('row overflow returns explicit limit error',lc.scan(limitkey,False)['code']==1080000051)
    check('overflow creates no partial clean report or command',report_counts()==counts)
    b.stop(limited);check('same key can recover after server bound restored',c.scan(limitkey)['differenceCount']==0)
    snapshot_test(c,f)
    b.stop(a);a=start('restart',48082);c=Client(48082).login()
    check('run key persists after JVM restart',c.scan(key)==clean)
    check('review key persists after JVM restart',c.review(item,'已核实为独立测试注入，保留报告原始差异',reviewkey)==review)
    check('current clean report after concurrency restart',c.scan()['differenceCount']==0)
    E['result']='passed'

def permissions(c,clean,dirty,item,key):
    menus=[x[0] for x in sql("SELECT id FROM system_menu WHERE deleted=0 AND (permission LIKE 'erp:%%' OR permission LIKE 'fulfillment:%%' OR id=597)")]
    role=c.api('POST','/system/role/create',{'name':RUN,'code':RUN,'status':0,'sort':1})
    def grant(ids):c.api('POST','/system/permission/assign-role-menu',{'roleId':role,'menuIds':ids})
    grant(menus)
    def user(suffix,assign=True):
        name=RUN+suffix;uid=c.api('POST','/system/user/create',{'username':name,'nickname':name,'password':'admin123'})
        if assign:c.api('POST','/system/permission/assign-user-role',{'userId':uid,'roleIds':[role]})
        return Client(48082).login(name)
    audit=user('Audit');other=user('Other');none=user('None',False)
    check('anonymous query denied',Client(48082).api('GET','/fulfillment/reconcile/page',ok=False)['code']==401)
    check('no function permission cannot scan',none.scan(ok=False)['code']==403)
    check('no function permission cannot query',none.api('GET','/fulfillment/reconcile/get',params={'id':clean['id']},ok=False)['code']==403)
    ownkey='audit-'+RUN;own=audit.scan(ownkey,extra={'tenantId':999999,'actorId':1,'warehouseId':999999});check('authorized audit scope ignores injected actor tenant filters',own['differenceCount']==0 and own['scannedCount']==clean['scannedCount'])
    check('other audit actor cannot get known report',other.api('GET','/fulfillment/reconcile/get',params={'id':own['id']},ok=False)['code']==1080000050)
    check('other audit actor cannot list known findings',other.api('GET','/fulfillment/reconcile/items',params={'runId':own['id']},ok=False)['code']==1080000050)
    check('other actor cannot review known difference',audit.review(item,'越权',ok=False)['code']==1080000050)
    check('audit page only own reports',audit.api('GET','/fulfillment/reconcile/page')['total']==1)
    grant([i for i in menus if i!=50014]);check('revoked run permission blocks successful replay',audit.scan(ownkey,False)['code']==403);grant(menus)
    grant([i for i in menus if i!=50013]);check('run also requires query permission',audit.scan(ok=False)['code']==403);grant(menus)
    check('restored permission returns original result',audit.scan(ownkey)==own)
    package=c.api('POST','/system/tenant-package/create',{'name':RUN,'status':0,'menuIds':menus})
    tid=c.api('POST','/system/tenant/create',{'name':RUN+'租户','contactName':'M4.3','status':0,'packageId':package,'expireTime':'2035-12-31T23:59:59','accountCount':10,'username':RUN+'Tenant','password':'admin123','websites':[]})
    foreign=Client(48082,tid).login(RUN+'Tenant');empty=foreign.scan();check('foreign tenant sees empty tenant snapshot',empty['scannedCount']==0 and empty['differenceCount']==0)
    check('foreign tenant cannot get known report',foreign.api('GET','/fulfillment/reconcile/get',params={'id':clean['id']},ok=False)['code']==1080000050)
    check('foreign tenant cannot review known difference',foreign.review(item,'越租户',ok=False)['code']==1080000050)

def snapshot_test(c,f):
    # A separate connection owns the named barrier. A normal HTTP writer commits
    # AFTER inventory was read but BEFORE the remaining tables are read.
    p=start('snapshot',48083,'--fulfillment.test.reconcile-barrier=true');sc=Client(48083).login();name='m4c:'+DATABASE
    with db() as con:
        with con.cursor() as cur:cur.execute('SELECT GET_LOCK(%s,0)',(name,));check('snapshot barrier owned',cur.fetchone()[0]==1)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(sc.scan)
            try:
                b.wait_for(lambda:'M4_RECONCILE_SNAPSHOT_READY' in (ROOT/'.local/m4-reconcile-snapshot-out.log').read_text(encoding='utf-8',errors='replace'))
                check('busy admission rejects before claiming a command',sc.scan('busy-'+RUN,False)['code']==1080000052 and not sql("SELECT id FROM ful_command_record WHERE idempotency_key=%s",('busy-'+RUN,)))
                fresh=f.shipment('快照并发写',('2.000001',));ret=c.create_return(fresh['order'],fresh['shipment'],[(fresh['lines'][0]['id'],'1.000001')]);c.receive(fresh['order'],ret['id']);E['concurrent_fixture']=fresh
            finally:
                with con.cursor() as cur:cur.execute('SELECT RELEASE_LOCK(%s)',(name,))
            snapshot=future.result();E['concurrent_snapshot']=snapshot
    check('writer committed while audit paused without business lock',b.balance(fresh)==(D(19),D(0)))
    check('RR snapshot does not mix old inventory with new shipment return',snapshot['differenceCount']==0,snapshot)
    latest=c.scan();check('new run sees committed rows absent from prior snapshot',latest['scannedCount']>snapshot['scannedCount'] and latest['differenceCount']==0)
    b.stop(p)

if __name__=='__main__':
    try:main()
    except Exception as error:E['result']='failed';E['error']=str(error);raise
    finally:
        for p,out in OWNED:b.stop(p);out.close()
        E['all_owned_processes_stopped']=all(p.poll() is not None for p,_ in OWNED)
        for path in (ROOT/'.local').glob('m4-reconcile-*-out.log'):shutil.copyfile(path,ROOT/'../学习资料/10-验收证据'/('M4.3-'+path.name))
        (ROOT/'../学习资料/10-验收证据/M4.3-reconcile-acceptance.json').write_text(json.dumps(E,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
        print('M4.3 acceptance',E.get('result'),len(E['checks']),'checks',DATABASE,flush=True)
