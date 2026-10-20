"""M4.2 independent real MySQL/HTTP/JVM acceptance. Fixtures via public APIs.
SQL is read-only except rollback-only negative constraint probes. Keeps labelled data.
"""
import concurrent.futures,json,os,shutil,socket,subprocess,sys,threading,time,uuid
from datetime import datetime,timezone
from decimal import Decimal as D
from m1_acceptance import ROOT,db,sql
from m3_acceptance import M3Client

DATABASE=os.getenv('M4_RETURN_DATABASE','fulfillment_m4_return_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
os.environ['DB_NAME']=DATABASE
RUN='M4R'+uuid.uuid4().hex[:8];NOW=datetime.now().isoformat(timespec='seconds')
E={'run_at':datetime.now(timezone.utc).isoformat(),'database':DATABASE,'redis_database':5,'checks':[],'commands':[],'processes':[],'ids':{}}
OWNED=[];JAR=ROOT/'.local/m4-return-run.jar'

def check(name,ok,detail=None):
    E['checks'].append({'name':name,'passed':bool(ok),'detail':detail})
    print(('PASS ' if ok else 'FAIL ')+name,flush=True)
    if not ok:raise AssertionError(name+': '+str(detail))
def wait_for(predicate,seconds=65):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        value=predicate()
        if value:return value
        time.sleep(.3)
    raise AssertionError('Timeout waiting for condition')
def start(name,profile='',during=False,port=48083):
    env=os.environ.copy();env['APP_PORT']=str(port)
    out=(ROOT/'.local'/('m4-return-'+name+'-out.log')).open('wb')
    args=[shutil.which('java'),'-Xms128m','-Xmx768m','-Dfile.encoding=UTF-8','-Duser.timezone=Asia/Shanghai','-jar',str(JAR),
          '--spring.profiles.active=fulfillment'+(','+profile if profile else ''),'--spring.data.redis.database=5',
          '--logging.file.name=../.local/m4-return-'+name+'-app.log']
    if during:args+=['--fulfillment.test.return-fail-during-erp=true']
    p=subprocess.Popen(args,cwd=ROOT/'backend',env=env,stdout=out,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    OWNED.append((p,out));E['processes'].append({'name':name,'port':port,'pid':p.pid,'profiles':profile,'during_erp':during})
    def ready():
        if p.poll() is not None:raise AssertionError('JVM exited '+name)
        try:return M3Client(port).login()
        except Exception:return False
    wait_for(ready);return p
def stop(p):
    if p.poll() is None:
        p.terminate()
        try:p.wait(20)
        except subprocess.TimeoutExpired:p.kill();p.wait(10)
def shell(file,*args):
    path=ROOT/'.local'/('m4-return-'+str(len(E['commands']))+'.log')
    with path.open('wb') as out:r=subprocess.run([os.environ['M0_PWSH'],'-NoProfile','-File',str(ROOT/file),*args],cwd=ROOT,stdout=out,stderr=subprocess.STDOUT,timeout=180)
    E['commands'].append({'script':file,'arguments':args,'exit_code':r.returncode,'log':str(path.relative_to(ROOT))})
    check('setup command '+file+' '+str(args),r.returncode==0)

class Client(M3Client):
    def create_return(self,order,shipment,lines,key=None,ok=True,extra=None):
        return self.api('POST','/fulfillment/return/create',{'orderId':str(order),'shipmentId':str(shipment),'items':[{'id':str(i),'quantity':str(q)} for i,q in lines],'reason':'商品退回'+RUN,**(extra or {})},headers={'Idempotency-Key':key or uuid.uuid4().hex},ok=ok)
    def receive(self,order,r,key=None,ok=True):
        return self.api('POST','/fulfillment/return/receive',{'orderId':str(order),'returnId':str(r)},headers={'Idempotency-Key':key or uuid.uuid4().hex},ok=ok)
    def reject(self,order,r,key=None,ok=True,reason='资料不完整'):
        return self.api('POST','/fulfillment/return/reject',{'orderId':str(order),'returnId':str(r),'reason':reason},headers={'Idempotency-Key':key or uuid.uuid4().hex},ok=ok)
    def return_get(self,r,ok=True):return self.api('GET','/fulfillment/return/get',params={'id':r},ok=ok)

class Fixture:
    def __init__(self,c,label):
        self.c=c;self.label=RUN+label
        self.unit=c.create('product-unit',{'name':self.label+'件','status':0})
        self.category=c.create('product-category',{'name':self.label,'code':self.label,'parentId':0,'sort':1,'status':0})
        self.customer=c.create('customer',{'name':self.label+'客户','status':0,'sort':1})
        self.supplier=c.create('supplier',{'name':self.label+'供方','status':0,'sort':1})
        self.account=c.create('account',{'name':self.label+'账户','no':self.label,'status':0,'sort':1})
        self.w=c.create('warehouse',{'name':self.label+'原发货仓','status':0,'sort':1,'warehousePrice':'0','truckagePrice':'0'})
    def shipment(self,label,quantities=('6.000001',),ordered=None,client=None):
        c=client or self.c;p=c.create('product',{'name':self.label+label,'barCode':self.label+label,'categoryId':self.category,'unitId':self.unit,'status':0,'salePrice':'2.345678','purchasePrice':'0'})
        inc=c.create('stock-in',{'supplierId':self.supplier,'inTime':NOW,'items':[{'productId':p,'warehouseId':self.w,'count':'20','productPrice':'0'}]});c.approve('stock-in',inc)
        source=c.create('sale-order',{'customerId':self.customer,'accountId':self.account,'orderTime':NOW,'discountPercent':'5','items':[{'productId':p,'count':ordered or q,'productPrice':'2.345678','taxPercent':'13'} for q in quantities]})
        c.approve('sale-order',source);order=c.bind(source)['orderId'];alloc=c.allocate(order,[self.w])['reservations']
        shipped=c.ship(order,self.w,[(a['id'],q) for a,q in zip(alloc,quantities)])
        detail=c.api('GET','/fulfillment/order/get',params={'id':order})
        if ordered:c.cancel(order,[(detail['items'][0]['id'],str(D(ordered)-D(quantities[0])))])
        ship=c.api('GET','/fulfillment/shipment/get',params={'id':shipped['shipmentId']})
        fixture={'product':p,'source':source,'order':order,'shipment':shipped['shipmentId'],'lines':ship['items'],'warehouse':self.w}
        E['ids'][label]=fixture;return fixture

def balance(f):return sql('SELECT `count`,ful_reserved_count FROM erp_stock WHERE product_id=%s AND warehouse_id=%s',(f['product'],f['warehouse']))[0]
def amounts(f):return sql('SELECT open_qty,reserved_qty,shipped_qty,cancelled_qty,returned_qty FROM ful_order_item WHERE order_id=%s ORDER BY id',(f['order'],))
def facts(f):return {'stock':balance(f),'items':amounts(f),'erp_return':sql('SELECT id,status FROM erp_sale_return WHERE order_id=%s',(f['source'],)),
    'physical':sql('SELECT id,`count`,total_count FROM erp_stock_record WHERE product_id=%s ORDER BY id',(f['product'],)),
    'head':sql('SELECT id,status,erp_sale_return_id,received_at,rejected_at FROM ful_return WHERE order_id=%s ORDER BY id',(f['order'],)),
    'rows':sql('SELECT id,quantity,erp_sale_return_item_id,erp_stock_record_id FROM ful_return_item WHERE order_id=%s ORDER BY id',(f['order'],)),
    'source':sql('SELECT out_count,return_count FROM erp_sale_order_items WHERE order_id=%s ORDER BY id',(f['source'],)),
    'version':sql('SELECT version,status FROM ful_order WHERE id=%s',(f['order'],))}

def invariants():
    check('all H R reservations and both ledgers agree',not sql('SELECT s.id FROM erp_stock s WHERE s.`count`<s.ful_reserved_count OR s.ful_reserved_count<0 OR s.ful_reserved_count<>(SELECT COALESCE(SUM(r.held_qty),0) FROM ful_reservation r WHERE r.tenant_id=s.tenant_id AND r.product_id=s.product_id AND r.warehouse_id=s.warehouse_id) OR s.ful_reserved_count<>(SELECT COALESCE(SUM(l.held_delta),0) FROM ful_stock_ledger l WHERE l.tenant_id=s.tenant_id AND l.product_id=s.product_id AND l.warehouse_id=s.warehouse_id) OR s.`count`<>(SELECT COALESCE(SUM(l.`count`),0) FROM erp_stock_record l WHERE l.tenant_id=s.tenant_id AND l.product_id=s.product_id AND l.warehouse_id=s.warehouse_id)'))
    check('all received quantities match order returned aggregates',not sql("SELECT i.id FROM ful_order_item i WHERE i.returned_qty<>(SELECT COALESCE(SUM(ri.quantity),0) FROM ful_return_item ri JOIN ful_return r ON r.id=ri.return_id AND r.tenant_id=ri.tenant_id WHERE ri.tenant_id=i.tenant_id AND ri.order_item_id=i.id AND r.status='RECEIVED')"))
    check('all live applications and receipts respect each original shipment item',not sql("SELECT s.id FROM ful_shipment_item s WHERE s.quantity<(SELECT COALESCE(SUM(i.quantity),0) FROM ful_return_item i JOIN ful_return r ON r.tenant_id=i.tenant_id AND r.id=i.return_id WHERE i.tenant_id=s.tenant_id AND i.shipment_item_id=s.id AND r.status IN ('REQUESTED','RECEIVED'))"))
    check('every received return links approved same-tenant ERP document',not sql("SELECT r.id FROM ful_return r LEFT JOIN erp_sale_return e ON e.id=r.erp_sale_return_id AND e.tenant_id=r.tenant_id WHERE r.status='RECEIVED' AND (e.id IS NULL OR e.deleted<>0 OR e.status<>20 OR e.order_id<>(SELECT erp_order_id FROM ful_order WHERE id=r.order_id))"))
    check('every receipt item matches positive ERP physical effect once',not sql("SELECT i.id FROM ful_return_item i JOIN ful_return r ON r.id=i.return_id LEFT JOIN erp_sale_return_items e ON e.id=i.erp_sale_return_item_id AND e.tenant_id=i.tenant_id LEFT JOIN erp_stock_record s ON s.id=i.erp_stock_record_id AND s.tenant_id=i.tenant_id WHERE r.status='RECEIVED' AND (e.id IS NULL OR s.id IS NULL OR e.return_id<>r.erp_sale_return_id OR e.`count`<>i.quantity OR e.warehouse_id<>r.warehouse_id OR s.`count`<>i.quantity OR s.biz_type<>60 OR s.biz_id<>r.erp_sale_return_id OR s.biz_item_id<>e.id)"))
    check('only received rows have ERP item mappings',not sql("SELECT i.id FROM ful_return_item i JOIN ful_return r ON r.id=i.return_id WHERE (r.status='RECEIVED')<>(i.erp_sale_return_item_id IS NOT NULL AND i.erp_stock_record_id IS NOT NULL)"))

def main():
    for port in [48082,48083]:
        with socket.socket() as s:check('test port free '+str(port),s.connect_ex(('127.0.0.1',port))!=0)
    shell('scripts/Initialize-Database.ps1','-Database',DATABASE)
    for action in ['baseline','migrate','validate']:shell('scripts/Migrate-Database.ps1','-Action',action,'-Database',DATABASE)
    shutil.copyfile(ROOT/'backend/yudao-server/target/yudao-server.jar',JAR)
    a=start('a',port=48082);admin=Client(48082).login();f=Fixture(admin,'A')
    env=os.environ.copy();env.update(API_BASE='http://127.0.0.1:48082',M1_EVIDENCE='M4.2-clean-binding.json')
    with (ROOT/'.local/m4-return-m1.log').open('wb') as out:r=subprocess.run([sys.executable,str(ROOT/'tests/m1_acceptance.py')],env=env,stdout=out,stderr=subprocess.STDOUT,timeout=150)
    check('new database M1 source auth and binding regression',r.returncode==0)
    check('new database history 0 through 4',tuple(x[0] for x in sql('SELECT version FROM ful_flyway_schema_history ORDER BY installed_rank'))==('0','1','2','3','4'))
    fx=f.shipment('精度闭环',ordered='10.000001');sid=fx['lines'][0]['id'];order=fx['order']
    initial=facts(fx);key='create-'+RUN
    request=admin.create_return(order,fx['shipment'],[(sid,'2.000001')],key,extra={'warehouseId':'999999','productPrice':'0','tenantId':999})
    check('request is pending and changes no H R or order quantities',request['status']=='REQUESTED' and balance(fx)==initial['stock'] and amounts(fx)==initial['items'])
    check('create decimal and reason normalized replay',admin.create_return(order,fx['shipment'],[(sid,'2.000001')],key)==request)
    check('same create key changed content conflicts',admin.create_return(order,fx['shipment'],[(sid,'2')],key,ok=False)['code']==1080000005)
    pending=admin.create_return(order,fx['shipment'],[(sid,'3')]);check('pending requests consume return allowance',admin.create_return(order,fx['shipment'],[(sid,'1.000001')],ok=False)['code']==1080000041)
    check('zero quantity rejected',admin.create_return(order,fx['shipment'],[(sid,'0')],ok=False)['code']==1080000011)
    check('duplicate shipment item rejected',admin.create_return(order,fx['shipment'],[(sid,'1'),(sid,'1')],ok=False)['code']==1080000011)
    check('unowned shipment item rejected',admin.create_return(order,fx['shipment'],[('9223372036854775807','1')],ok=False)['code']==1080000022)
    check('sub-micro precision rejected',admin.create_return(order,fx['shipment'],[(sid,'0.0000001')],ok=False)['code']==400)
    reject_key='reject-'+RUN;rejected=admin.reject(order,pending['id'],reject_key)
    check('rejection releases allowance without changing inventory',rejected['status']=='REJECTED' and balance(fx)==initial['stock'])
    check('rejection replay remains stable',admin.reject(order,pending['id'],reject_key)==rejected)
    check('rejected application cannot be received',admin.receive(order,pending['id'],ok=False)['code']==1080000042)
    later=admin.create_return(order,fx['shipment'],[(sid,'4')]);admin.reject(order,later['id'])

    # Two fault locations, same request/key. No physical or domain fact may survive either exception.
    receipt_key='receive-'+RUN
    for name,during,marker in [('after',False,'M4_RETURN_FAILURE_AFTER_ERP'),('during',True,'M4_RETURN_FAILURE_DURING_ERP')]:
        b=start(name,'fulfillment-return-fault-test',during)
        before=facts(fx);failure=Client(48083).login().receive(order,request['id'],receipt_key,ok=False)
        check(name+' ERP test fault actually reached',failure['code']==500 and marker in (ROOT/'.local'/('m4-return-'+name+'-out.log')).read_text(encoding='utf-8',errors='replace'))
        check(name+' fault rolls back H R aggregate ERP document and mappings',before==facts(fx))
        check(name+' failed receive command rolled back',not sql("SELECT id FROM ful_command_record WHERE command_type='RETURN_RECEIVE' AND idempotency_key=%s",(receipt_key,)))
        stop(b)
    b=start('b');second=Client(48083).login()
    received=admin.receive(order,request['id'],receipt_key)
    check('healthy retry after both failures receives exactly once',received['status']=='RECEIVED' and balance(fx)==(D(16),D(0)))
    check('gross shipped cancelled open and terminal status preserved',amounts(fx)==((D(0),D(0),D('6.000001'),D(4),D('2.000001')),) and received['orderStatus']=='PARTIALLY_CLOSED')
    check('same receive key replay stable across JVMs',second.receive(order,request['id'],receipt_key)==received)
    check('new receive key on received return has no new effect',second.receive(order,request['id'])==received and len(sql('SELECT id FROM erp_sale_return WHERE order_id=%s',(fx['source'],)))==1)
    check('received return cannot be rejected',admin.reject(order,request['id'],ok=False)['code']==1080000042)
    check('create replay returns original pending response after receipt',admin.create_return(order,fx['shipment'],[(sid,'2.000001')],key)==request)
    check('one micro over remaining allowance rejected',admin.create_return(order,fx['shipment'],[(sid,'4.000001')],ok=False)['code']==1080000041)
    view=admin.return_get(request['id']);check('origin warehouse ignores forged body and receipt mappings present',view['warehouseId']==str(f.w) and all(view['items'][0][k] for k in ['erpSaleReturnItemId','erpStockRecordId']))
    check('ERP source returnCount updated without reducing outCount',sql('SELECT out_count,return_count FROM erp_sale_order_items WHERE order_id=%s',(fx['source'],))==((D('6.000001'),D('2.000001')),))
    check('original price tax and warehouse reused; refund remains zero',sql('SELECT product_price,tax_percent,warehouse_id FROM erp_sale_return_items WHERE return_id=%s',(received['erpSaleReturnId'],))==((D('2.345678'),D(13),f.w),) and sql('SELECT refund_price FROM erp_sale_return WHERE id=%s',(received['erpSaleReturnId'],))[0][0]==0)
    for method,path,params,body in [('PUT','/erp/sale-return/update-status',{'id':received['erpSaleReturnId'],'status':10},None),('DELETE','/erp/sale-return/delete',{'ids':received['erpSaleReturnId']},None),('POST','/erp/sale-return/create',None,{'orderId':fx['source'],'returnTime':NOW,'managed':True,'internal':True,'items':[]})]:
        check('legacy managed mutation frozen '+path,admin.api(method,path,body,params,ok=False)['code']==1030199000)

    # Same-key creation and over-allocation across two distinct JVMs.
    cf=f.shipment('并发申请',('5',));csid=cf['lines'][0]['id'];same='same-'+RUN;barrier=threading.Barrier(6)
    def create_same(n):
        c=Client(48082 if n%2==0 else 48083).login();barrier.wait();return c.create_return(cf['order'],cf['shipment'],[(csid,'2')],same)
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:created=list(pool.map(create_same,range(6)))
    check('two JVM same-key applications create one fact',all(x==created[0] for x in created) and sql('SELECT COUNT(*) FROM ful_return WHERE order_id=%s',(cf['order'],))[0][0]==1)
    barrier=threading.Barrier(4)
    def over(n):
        c=Client(48082 if n%2==0 else 48083).login();barrier.wait();return c.create_return(cf['order'],cf['shipment'],[(csid,'2')],ok=False)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:competing=list(pool.map(over,range(4)))
    check('pending plus received cap serialized across JVMs',sum(x['code']==0 for x in competing)==1 and all(x['code'] in (0,1080000041) for x in competing),competing)
    barrier=threading.Barrier(6);same_receipt='same-receive-'+RUN
    def receive_same(n):
        c=Client(48082 if n%2==0 else 48083).login();barrier.wait();return c.receive(cf['order'],created[0]['id'],same_receipt)
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(receive_same,range(6)))
    check('T17 two JVM repeated receipts yield one ERP effect',all(x==results[0] for x in results) and balance(cf)==(D(17),D(0)) and sql('SELECT COUNT(*) FROM erp_sale_return WHERE order_id=%s',(cf['source'],))[0][0]==1)
    race=f.shipment('收货拒绝竞争',('3',));rr=admin.create_return(race['order'],race['shipment'],[(race['lines'][0]['id'],'2')])
    barrier=threading.Barrier(2)
    def terminal(n):
        c=Client(48082 if n==0 else 48083).login();barrier.wait();return c.receive(race['order'],rr['id'],ok=False) if n==0 else c.reject(race['order'],rr['id'],ok=False)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(terminal,range(2)))
    status=admin.return_get(rr['id'])['status'];check('receive versus reject admits one terminal transition',sum(x['code']==0 for x in results)==1 and all(x['code'] in (0,1080000042) for x in results) and balance(race)==(D(19) if status=='RECEIVED' else D(17),D(0)),results)
    multi=f.shipment('重复商品两行',('3','4'));mr=admin.create_return(multi['order'],multi['shipment'],[(x['id'],q) for x,q in zip(multi['lines'],('1.000001','2.000002'))]);admin.receive(multi['order'],mr['id'])
    check('duplicate SKU lines preserve item identity and exact stock',balance(multi)==(D('16.000003'),D(0)) and [x[4] for x in amounts(multi)]==[D('1.000001'),D('2.000002')])
    last=admin.create_return(order,fx['shipment'],[(sid,'4')]);admin.receive(order,last['id'])
    check('full return restores physical gross shipped stays and order stays closed',balance(fx)==(D(20),D(0)) and amounts(fx)==((D(0),D(0),D('6.000001'),D(4),D('6.000001')),))
    check('full returned order has no automatically reopened allocation',admin.allocate(order,[f.w])['outcome']=='NOTHING_TO_ALLOCATE')
    check('return page is paginated with string quantities',len(admin.api('GET','/fulfillment/return/page',params={'orderId':order,'pageSize':2})['list'])==2 and isinstance(view['items'][0]['quantity'],str))
    check('return page limit enforced',admin.api('GET','/fulfillment/return/page',params={'orderId':order,'pageSize':101},ok=False)['code']==400)

    permissions(admin,f)
    # MySQL FK/CHECK negative probes are always rolled back.
    with db() as connection:
        connection.begin()
        try:
            try:connection.cursor().execute("UPDATE ful_return SET status='RECEIVED' WHERE id=%s",(pending['id'],));check('DB rejects received state without receipt links',False)
            except Exception as error:check('DB rejects received state without receipt links',getattr(error,'args',[0])[0]==3819)
        finally:connection.rollback()
    invariants()
    # Stop both JVMs with durable receipt facts, restart and replay the original receipt key.
    before=facts(fx);stop(a);stop(b);a=start('restart',port=48082)
    replay=Client(48082).login().receive(order,request['id'],receipt_key)
    check('receipt key survives JVM restart unchanged',replay==received and facts(fx)==before)
    E['result']='passed'

def permissions(admin,f):
    menus=[x[0] for x in sql("SELECT id FROM system_menu WHERE deleted=0 AND (permission LIKE 'erp:%%' OR permission LIKE 'fulfillment:%%' OR id=597)")]
    role=admin.api('POST','/system/role/create',{'name':RUN,'code':RUN,'status':0,'sort':1})
    def grant(ids):admin.api('POST','/system/permission/assign-role-menu',{'roleId':role,'menuIds':ids})
    grant(menus)
    def user(suffix,assign=True):
        name=RUN+suffix;uid=admin.api('POST','/system/user/create',{'username':name,'nickname':name,'password':'admin123'})
        if assign:admin.api('POST','/system/permission/assign-user-role',{'userId':uid,'roleIds':[role]})
        return Client(48082).login(name)
    owner=user('Owner');other=user('Other');none=user('None',False)
    target=f.shipment('归属权限',('4',),client=owner);sid=target['lines'][0]['id'];oid=target['order']
    request=owner.create_return(oid,target['shipment'],[(sid,'2')]);key='auth-'+RUN;received=owner.receive(oid,request['id'],key)
    check('ordinary owner receives own return',received['status']=='RECEIVED')
    for c,code,label in [(none,403,'no permission'),(other,1080000003,'wrong owner')]:
        check('create '+label,c.create_return(oid,target['shipment'],[(sid,'1')],ok=False)['code']==code)
        check('receive '+label,c.receive(oid,request['id'],key,ok=False)['code']==code)
        check('reject '+label,c.reject(oid,request['id'],ok=False)['code']==code)
        check('get '+label,c.return_get(request['id'],ok=False)['code']==code)
    grant([x for x in menus if x!=50011]);check('receipt replay rechecks revoked function permission',owner.receive(oid,request['id'],key,ok=False)['code']==403);grant(menus)
    check('restored permission permits original replay',owner.receive(oid,request['id'],key)==received)
    package=admin.api('POST','/system/tenant-package/create',{'name':RUN+'套餐','status':0,'menuIds':menus})
    tenant=admin.api('POST','/system/tenant/create',{'name':RUN+'隔离租户','contactName':'M4.2','status':0,'packageId':package,'expireTime':'2035-12-31T23:59:59','accountCount':10,'username':RUN+'Tenant','password':'admin123','websites':[]})
    foreign=Client(48082,tenant).login(RUN+'Tenant')
    check('foreign tenant cannot read known return',foreign.return_get(request['id'],ok=False)['code']==1080000040)
    check('foreign tenant cannot receive known order',foreign.receive(oid,request['id'],ok=False)['code']==1080000003)
    check('foreign tenant cannot list known order returns',foreign.api('GET','/fulfillment/return/page',params={'orderId':oid},ok=False)['code']==1080000003)
    ff=Fixture(foreign,'B');fx=ff.shipment('外租户退回',('2',));r=foreign.create_return(fx['order'],fx['shipment'],[(fx['lines'][0]['id'],'1')]);foreign.receive(fx['order'],r['id'])
    check('foreign tenant can receive own goods in original warehouse',balance(fx)==(D(19),D(0)))
    check('tenant one cannot mutate foreign receipt',admin.receive(fx['order'],r['id'],ok=False)['code']==1080000003)

if __name__=='__main__':
    try:main()
    except Exception as error:E['result']='failed';E['error']=str(error);raise
    finally:
        for process,out in OWNED:stop(process);out.close()
        E['all_owned_processes_stopped']=all(p.poll() is not None for p,_ in OWNED)
        for path in (ROOT/'.local').glob('m4-return-*-out.log'):shutil.copyfile(path,ROOT/'../学习资料/10-验收证据'/('M4.2-'+path.name))
        (ROOT/'../学习资料/10-验收证据/M4.2-return-acceptance.json').write_text(json.dumps(E,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
        print('M4.2 returns',E.get('result'),len(E['checks']),'checks',DATABASE,flush=True)
