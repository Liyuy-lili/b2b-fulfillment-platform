"""M1 real HTTP/MySQL acceptance. Creates labelled fixtures through public APIs.
Direct SQL: read-only assertions and a rollback-only CHECK probe. A malformed ERP
source created through HTTP proves fulfillment header/item/command atomic rollback.
No fake auth, no business table cleanup, no performance claims.
"""
import concurrent.futures,json,os,threading,uuid
from pathlib import Path
from datetime import datetime,timezone
from decimal import Decimal
import pymysql,requests

ROOT=Path(__file__).resolve().parents[1]
BASE=os.getenv('API_BASE','http://127.0.0.1:48080')+'/admin-api'
E={'run_at':datetime.now(timezone.utc).isoformat(),'api':BASE,'database':os.getenv('DB_NAME','fulfillment'),'checks':[],'ids':{}}
RUN='M1'+uuid.uuid4().hex[:8]
NOW=datetime.now().isoformat(timespec='seconds')

class Client:
    def __init__(self,tenant=1):
        self.s=requests.Session();self.s.headers['tenant-id']=str(tenant)
    def api(self,method,path,body=None,params=None,ok=True,headers=None):
        r=self.s.request(method,BASE+path,json=body,params=params,headers=headers,timeout=40)
        r.raise_for_status();data=r.json()
        if ok:
            if data.get('code')!=0:raise AssertionError(f'{method} {path}: {data}')
            return data.get('data')
        return data
    def login(self,name='admin'):
        token=self.api('POST','/system/auth/login',{'username':name,'password':'admin123'})
        self.s.headers['Authorization']='Bearer '+token['accessToken'];return self
    def create(self,kind,body):return self.api('POST','/erp/'+kind+'/create',body)
    def approve(self,kind,ident,status=20,ok=True):return self.api('PUT','/erp/'+kind+'/update-status',params={'id':ident,'status':status},ok=ok)
    def bind(self,source,key=None,ok=True,extra=None):return self.api('POST','/fulfillment/order/bind',{'erpOrderId':str(source),**(extra or {})},ok=ok,headers={'Idempotency-Key':key or uuid.uuid4().hex})

def check(name,condition,detail=None):
    E['checks'].append({'name':name,'passed':bool(condition),'detail':detail})
    if not condition and os.getenv('M1_DIAGNOSTIC')!='1':raise AssertionError(f'{name}: {detail}')
def db():return pymysql.connect(host='127.0.0.1',port=33306,user='fulfillment',password='fulfillment-dev',database=os.getenv('DB_NAME','fulfillment'),charset='utf8mb4',autocommit=True)
def sql(query,args=()):
    with db() as c:
        with c.cursor() as cur:cur.execute(query,args);return cur.fetchall()
def denied(name,result,code):check(name,result['code']==code,result)
def state():
    return {'stock':sql('SELECT id,`count` FROM erp_stock ORDER BY id'),
            'stock_records':sql('SELECT COUNT(*) FROM erp_stock_record')[0][0]}

def main():
    admin=Client().login()
    denied('anonymous denied',Client().api('GET','/fulfillment/order/page',ok=False),401)
    unit=admin.create('product-unit',{'name':RUN+'件','status':0})
    category=admin.create('product-category',{'name':RUN,'parentId':0,'code':RUN,'sort':1,'status':0})
    product=admin.create('product',{'name':RUN+'商品','barCode':RUN,'categoryId':category,'unitId':unit,'status':0,'purchasePrice':'8.25','salePrice':'12.5'})
    customer=admin.create('customer',{'name':RUN+'客户','status':0,'sort':1})
    account=admin.create('account',{'name':RUN+'账户','no':RUN,'status':0,'sort':1})
    warehouse=admin.create('warehouse',{'name':RUN+'西安仓','status':0,'sort':1,'warehousePrice':'0','truckagePrice':'0'})
    E['ids'].update(unit=unit,product=product,customer=customer,account=account,warehouse=warehouse)
    line={'productId':product,'productPrice':'12.5','count':'10.123456','taxPercent':'13'}
    body={'customerId':customer,'accountId':account,'orderTime':NOW,'discountPercent':'5','depositPrice':'1.23','items':[line]}
    def order(client=admin,approved=True):
        ident=client.create('sale-order',body)
        if approved:client.approve('sale-order',ident)
        return ident
    def outbound(source):
        source_detail=admin.api('GET','/erp/sale-order/get',params={'id':source})
        return {'orderId':source,'accountId':account,'outTime':NOW,'discountPercent':'0','otherPrice':'0',
                'items':[dict(line,count='1',taxPercent='0',orderItemId=source_detail['items'][0]['id'],warehouseId=warehouse)]}
    source=order();key=uuid.uuid4().hex;before=state()
    result=admin.bind(source,key,extra={'tenantId':999,'ownerUserId':'999','status':'FULFILLED'})
    check('bind creates order',isinstance(result['orderId'],str) and result['status']=='NEW',result)
    ful=result['orderId'];E['ids'].update(source=source,fulfillment=ful)
    check('same key replay stable',admin.bind(source,key)==result)
    check('different key same source stable',admin.bind(source)==result)
    check('one source one fulfillment',sql('SELECT COUNT(*) FROM ful_order WHERE tenant_id=1 AND erp_order_id=%s',(source,))[0][0]==1)
    detail=admin.api('GET','/fulfillment/order/get',params={'id':ful})
    item=detail['items'][0]
    check('six-place exact quantity snapshot',item['orderedQty']=='10.123456' and item['openQty']=='10.123456',item)
    check('initial inactive quantities zero',all(Decimal(item[k])==0 for k in ['reservedQty','shippedQty','cancelledQty','returnedQty']))
    check('actor tenant from server',detail['ownerUserId']=='1' and sql('SELECT tenant_id FROM ful_order WHERE id=%s',(ful,))[0][0]==1)
    check('ISO offset timestamp',detail['createTime'].endswith('Z') or detail['createTime'].endswith('+00:00'),detail['createTime'])
    for field in ['totalPrice','discountPercent','discountPrice','depositPrice']:
        check('decimal string '+field,isinstance(detail[field],str))
    source_detail=admin.api('GET','/erp/sale-order/get',params={'id':source})
    check('source monetary snapshot',Decimal(detail['totalPrice'])==Decimal(str(source_detail['totalPrice'])))
    another=order()
    denied('same key different request rejected',admin.bind(another,key,ok=False),1080000005)
    check('conflict does not create order',not sql('SELECT id FROM ful_order WHERE erp_order_id=%s',(another,)))
    draft=order(approved=False)
    failure_key=uuid.uuid4().hex
    denied('draft source rejected',admin.bind(draft,failure_key,ok=False),1080000001)
    check('failed command record rolls back',not sql('SELECT id FROM ful_command_record WHERE idempotency_key=%s',(failure_key,)))
    admin.approve('sale-order',draft)
    check('same key succeeds after failed transaction',admin.bind(draft,failure_key)['status']=='NEW')
    # Upstream accepts zero-count source lines. The second line fails after the new
    # header and first snapshot have been inserted, exercising a real transaction rollback.
    invalid_source=admin.create('sale-order',dict(body,items=[line,dict(line,count='0')]))
    admin.approve('sale-order',invalid_source)
    invalid_key='invalid'+RUN
    denied('invalid second line rejects binding',admin.bind(invalid_source,invalid_key,ok=False),1080000004)
    check('header rolled back after item validation failure',not sql('SELECT id FROM ful_order WHERE erp_order_id=%s',(invalid_source,)))
    check('first item rolled back after later failure',not sql('SELECT i.id FROM ful_order_item i JOIN erp_sale_order_items s ON s.id=i.erp_order_item_id WHERE s.order_id=%s',(invalid_source,)))
    check('command rolled back after later failure',not sql('SELECT id FROM ful_command_record WHERE idempotency_key=%s',(invalid_key,)))
    denied('missing source concealed',admin.bind(9223372036854775807,ok=False),1080000003)
    denied('overflow id validated',admin.bind('9999999999999999999',ok=False),1080000004)
    denied('missing key rejected',admin.api('POST','/fulfillment/order/bind',{'erpOrderId':str(another)},ok=False),400)
    denied('bad key rejected',admin.api('POST','/fulfillment/order/bind',{'erpOrderId':str(another)},ok=False,headers={'Idempotency-Key':'bad key'}),400)

    # The guard executes before old approved-state checks, yielding a clear managed-order error.
    denied('source unaudit frozen',admin.approve('sale-order',source,10,ok=False),1030199000)
    denied('source edit frozen',admin.api('PUT','/erp/sale-order/update',dict(body,id=source),ok=False),1030199000)
    denied('source delete frozen',admin.api('DELETE','/erp/sale-order/delete',params={'ids':source},ok=False),1030199000)
    denied('manual outbound frozen',admin.api('POST','/erp/sale-out/create',outbound(source),ok=False),1030199000)
    ret=dict(outbound(source));ret['returnTime']=ret.pop('outTime')
    denied('manual return frozen',admin.api('POST','/erp/sale-return/create',ret,ok=False),1030199000)
    check('binding and rejected writes leave inventory unchanged',state()==before)
    used=order();out_id=admin.create('sale-out',outbound(used))
    denied('draft outbound history blocks takeover',admin.bind(used,ok=False),1080000002)
    admin.api('DELETE','/erp/sale-out/delete',params={'ids':out_id})
    denied('deleted outbound history blocks takeover',admin.bind(used,ok=False),1080000002)
    moved_out=admin.create('sale-out',outbound(used))
    denied('cannot move existing outbound onto managed source',admin.api('PUT','/erp/sale-out/update',dict(outbound(source),id=moved_out),ok=False),1030199000)
    check('failed move retains old outbound source',admin.api('GET','/erp/sale-out/get',params={'id':moved_out})['orderId']==used)
    return_only=order();return_body=outbound(return_only);return_body['returnTime']=return_body.pop('outTime');return_body['items'][0]['count']='0'
    return_id=admin.create('sale-return',return_body)
    denied('return-only history blocks takeover',admin.bind(return_only,ok=False),1080000002)
    admin.api('DELETE','/erp/sale-return/delete',params={'ids':return_id})
    denied('deleted return-only history blocks takeover',admin.bind(return_only,ok=False),1080000002)

    # Race different command keys against the same source. Unique business key + source lock must converge.
    concurrent_source=order();barrier=threading.Barrier(8)
    def race(index):
        c=Client();c.s.headers.update(admin.s.headers);barrier.wait();return c.bind(concurrent_source,'race'+RUN+str(index))
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(race,range(8)))
    check('eight concurrent bind requests converge',len({r['orderId'] for r in results})==1,results)
    check('concurrent binding inserts one snapshot',sql('SELECT COUNT(*) FROM ful_order WHERE erp_order_id=%s',(concurrent_source,))[0][0]==1)
    # Same key race also exercises command-row serialization, rather than only the source lock.
    same_source=order();barrier=threading.Barrier(6)
    def same_race(_):
        c=Client();c.s.headers.update(admin.s.headers);barrier.wait();return c.bind(same_source,'same'+RUN)
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(same_race,range(6)))
    check('six concurrent identical commands converge',len({r['orderId'] for r in results})==1)
    check('one command result persisted',sql("SELECT COUNT(*) FROM ful_command_record WHERE idempotency_key=%s",('same'+RUN,))[0][0]==1)

    race_outcomes=[]
    for n in range(8):
        target=order();out_body=outbound(target);start=threading.Barrier(2)
        def competing_bind():
            c=Client();c.s.headers.update(admin.s.headers);start.wait();return c.bind(target,ok=False)
        def competing_out():
            c=Client();c.s.headers.update(admin.s.headers);start.wait();return c.api('POST','/erp/sale-out/create',out_body,ok=False)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            a=pool.submit(competing_bind);b=pool.submit(competing_out);bound,old_out=a.result(),b.result()
        valid=(bound['code']==0 and old_out['code']==1030199000) or (old_out['code']==0 and bound['code']==1080000002)
        check('bind versus old outbound race '+str(n),valid,{'bind_code':bound['code'],'out_code':old_out['code']})
        race_outcomes.append({'source':target,'bind_code':bound['code'],'out_code':old_out['code']})
    E['bind_out_races']=race_outcomes

    # Role-based auth fixtures are created/granted through the existing admin endpoints.
    menu_ids=[r[0] for r in sql("SELECT id FROM system_menu WHERE deleted=0 AND (permission LIKE 'erp:%%' OR id IN (597,50000,50001))")]
    role=admin.api('POST','/system/role/create',{'name':RUN+'操作员','code':RUN,'status':0,'sort':1})
    admin.api('POST','/system/permission/assign-role-menu',{'roleId':role,'menuIds':menu_ids})
    def user(suffix,with_role=True):
        name=RUN+suffix
        ident=admin.api('POST','/system/user/create',{'username':name,'nickname':name,'password':'admin123'})
        if with_role:admin.api('POST','/system/permission/assign-user-role',{'userId':ident,'roleIds':[role]})
        return ident,Client().login(name)
    alice_id,alice=user('Alice');bob_id,bob=user('Bob');_,no_role=user('None',False)
    denied('no function permission rejected',no_role.bind(source,ok=False),403)
    alice_source=order(alice);alice_result=alice.bind(alice_source,'owner'+RUN)
    check('normal owner can bind own source',bool(alice_result['orderId']))
    denied('normal user cannot bind others source',bob.bind(alice_source,ok=False),1080000003)
    denied('normal user cannot read others fulfillment',bob.api('GET','/fulfillment/order/get',params={'id':alice_result['orderId']},ok=False),1080000003)
    page=bob.api('GET','/fulfillment/order/page',params={'pageNo':1,'pageSize':20})
    check('page scope excludes other owners',page['total']==0,page)
    owner_page=alice.api('GET','/fulfillment/order/page',params={'pageNo':1,'pageSize':20})
    check('owner page scope',owner_page['total']==1 and owner_page['list'][0]['id']==alice_result['orderId'])
    check('administrator can read others',admin.api('GET','/fulfillment/order/get',params={'id':alice_result['orderId']})['ownerUserId']==str(alice_id))
    # Revoke bind permission and try the already successful key; replay must not bypass current RBAC.
    admin.api('POST','/system/permission/assign-role-menu',{'roleId':role,'menuIds':[i for i in menu_ids if i!=50001]})
    denied('replay rechecks current function permission',alice.bind(alice_source,'owner'+RUN,ok=False),403)
    admin.api('POST','/system/permission/assign-role-menu',{'roleId':role,'menuIds':menu_ids})

    package=admin.api('POST','/system/tenant-package/create',{'name':RUN+'隔离套餐','status':0,'menuIds':menu_ids})
    tenant=admin.api('POST','/system/tenant/create',{'name':RUN+'隔离租户','contactName':'M1测试','status':0,'packageId':package,'expireTime':'2035-12-31T23:59:59','accountCount':10,'username':RUN+'Tenant','password':'admin123','websites':[]})
    other=Client(tenant).login(RUN+'Tenant')
    denied('other tenant cannot bind known ERP id',other.bind(source,ok=False),1080000003)
    denied('other tenant cannot read known fulfillment id',other.api('GET','/fulfillment/order/get',params={'id':ful},ok=False),1080000003)
    other_page=other.api('GET','/fulfillment/order/page',params={'pageNo':1,'pageSize':10})
    check('other tenant page empty',other_page['total']==0)
    other_unit=other.create('product-unit',{'name':RUN+'隔离件','status':0})
    other_category=other.create('product-category',{'name':RUN+'隔离类','parentId':0,'code':RUN+'B','sort':1,'status':0})
    other_product=other.create('product',{'name':RUN+'隔离商品','barCode':RUN+'B','categoryId':other_category,'unitId':other_unit,'status':0,'salePrice':'3'})
    other_customer=other.create('customer',{'name':RUN+'隔离客户','status':0,'sort':1})
    other_source=other.create('sale-order',{'customerId':other_customer,'orderTime':NOW,'discountPercent':'0','items':[dict(line,productId=other_product,count='2')]})
    other.approve('sale-order',other_source)
    other_bound=other.bind(other_source)
    check('other tenant can bind own valid source',other_bound['status']=='NEW')
    other_detail=other.api('GET','/fulfillment/order/get',params={'id':other_bound['orderId']})
    check('other tenant sees own exact snapshot',other_detail['items'][0]['openQty']=='2.000000')
    denied('tenant one cannot read tenant two valid order',admin.api('GET','/fulfillment/order/get',params={'id':other_bound['orderId']},ok=False),1080000003)
    spoof=Client(tenant);spoof.s.headers.update(admin.s.headers);spoof.s.headers['tenant-id']=str(tenant)
    check('token cannot switch tenant header',spoof.api('GET','/fulfillment/order/get',params={'id':ful},ok=False)['code']!=0)
    E['ids'].update(alice=alice_id,bob=bob_id,tenant=tenant,role=role)

    with db() as c:
        c.begin()
        try:
            with c.cursor() as cur:
                try:
                    cur.execute('UPDATE ful_order_item SET open_qty=open_qty+1 WHERE id=%s',(item['id'],))
                    check('database quantity invariant rejects corruption',False)
                except pymysql.err.OperationalError as error:check('database quantity invariant rejects corruption',error.args[0]==3819,error.args[0])
        finally:c.rollback()
    check('rollback probe leaves quantity unchanged',admin.api('GET','/fulfillment/order/get',params={'id':ful})['items'][0]['openQty']=='10.123456')
    if any(not c['passed'] for c in E['checks']):raise AssertionError('Diagnostic run contains failed checks')
    E['result']='passed'

if __name__=='__main__':
    try:main()
    except Exception as exc:E['result']='failed';E['error']=str(exc);raise
    finally:
        (ROOT/'../学习资料/10-验收证据'/os.getenv('M1_EVIDENCE','M1-acceptance.json')).write_text(json.dumps(E,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
        print('M1',E.get('result'),len(E['checks']),'checks')
