"""M2 real HTTP/MySQL tests against two JVMs sharing the same DB and Redis.
No business SQL writes; direct SQL only reads plus deliberate rollback-only constraint probes.
"""
import concurrent.futures,json,os,threading,time,uuid
from datetime import datetime,timezone
from decimal import Decimal
import requests
from m1_acceptance import Client,ROOT,db,sql

E={'date':'2026-10-18','run_at':datetime.now(timezone.utc).isoformat(),'checks':[],'ids':{},'instances':['http://127.0.0.1:48080','http://127.0.0.1:48082']}
RUN='M2'+uuid.uuid4().hex[:8];NOW=datetime.now().isoformat(timespec='seconds')
class M2Client(Client):
    def __init__(self,port=48080,tenant=1):super().__init__(tenant);self.base=f'http://127.0.0.1:{port}/admin-api'
    def api(self,method,path,body=None,params=None,ok=True,headers=None):
        response=self.s.request(method,self.base+path,json=body,params=params,headers=headers,timeout=45)
        response.raise_for_status();result=json.loads(response.text,parse_float=Decimal)
        if ok:
            if result.get('code')!=0:raise AssertionError(f'{method} {path}: {result}')
            return result.get('data')
        return result
    def allocate(self,order,warehouses,strategy='PRIORITY_SPLIT',key=None,ok=True):
        return self.api('POST','/fulfillment/order/allocate',{'orderId':str(order),'warehouseIds':[str(w) for w in warehouses],'strategy':strategy,'holdSeconds':900},ok=ok,headers={'Idempotency-Key':key or uuid.uuid4().hex})
    def release(self,order,lines,key=None,ok=True):
        return self.api('POST','/fulfillment/order/release',{'orderId':str(order),'items':[{'reservationId':str(r),'quantity':str(q)} for r,q in lines],'reason':'M2 manual release'},ok=ok,headers={'Idempotency-Key':key or uuid.uuid4().hex})
def check(name,ok,detail=None):
    E['checks'].append({'name':name,'passed':bool(ok),'detail':detail})
    if not ok:raise AssertionError(name+': '+str(detail))
def balance(product,warehouse):
    rows=sql('SELECT `count`,ful_reserved_count FROM erp_stock WHERE tenant_id=1 AND product_id=%s AND warehouse_id=%s',(product,warehouse))
    return rows[0] if rows else (Decimal(0),Decimal(0))
def invariants(products):
    for p in products:
        for ident,warehouse,h,r in sql('SELECT id,warehouse_id,`count`,ful_reserved_count FROM erp_stock WHERE tenant_id=1 AND product_id=%s',(p,)):
            held=sql('SELECT COALESCE(SUM(held_qty),0) FROM ful_reservation WHERE tenant_id=1 AND product_id=%s AND warehouse_id=%s',(p,warehouse))[0][0]
            deltas=sql('SELECT COALESCE(SUM(held_delta),0) FROM ful_stock_ledger WHERE tenant_id=1 AND product_id=%s AND warehouse_id=%s',(p,warehouse))[0][0]
            physical=sql('SELECT COALESCE(SUM(`count`),0) FROM erp_stock_record WHERE tenant_id=1 AND product_id=%s AND warehouse_id=%s',(p,warehouse))[0][0]
            check('stock commitments equal reservations and ledger',Decimal(0)<=r<=h and r==held==deltas and h==physical,{'product':p,'warehouse':warehouse,'H':str(h),'R':str(r),'held':str(held),'ledger':str(deltas)})
            running=Decimal(0)
            for delta,after in sql('SELECT `count`,total_count FROM erp_stock_record WHERE tenant_id=1 AND product_id=%s AND warehouse_id=%s ORDER BY id',(p,warehouse)):
                running+=delta
                check('physical running ledger exact',running==after)
            running=Decimal(0)
            for delta,after in sql('SELECT held_delta,reserved_after FROM ful_stock_ledger WHERE tenant_id=1 AND product_id=%s AND warehouse_id=%s ORDER BY id',(p,warehouse)):
                running+=delta
                check('reservation running ledger exact',running==after)
def main():
    admin=M2Client().login();second=M2Client(48082).login()
    unit=admin.create('product-unit',{'name':RUN+'件','status':0})
    category=admin.create('product-category',{'name':RUN,'code':RUN,'parentId':0,'sort':1,'status':0})
    customer=admin.create('customer',{'name':RUN+'客户','status':0,'sort':1})
    supplier=admin.create('supplier',{'name':RUN+'供应商','status':0,'sort':1})
    account=admin.create('account',{'name':RUN+'账户','no':RUN,'status':0,'sort':1})
    wa=admin.create('warehouse',{'name':RUN+'优先仓','sort':1,'status':0,'warehousePrice':'0','truckagePrice':'0'})
    wb=admin.create('warehouse',{'name':RUN+'次选仓','sort':2,'status':0,'warehousePrice':'0','truckagePrice':'0'})
    disabled=admin.create('warehouse',{'name':RUN+'停用仓','sort':0,'status':1,'warehousePrice':'0','truckagePrice':'0'})
    all_products=[]
    def product(label):
        ident=admin.create('product',{'name':RUN+label,'barCode':RUN+label,'categoryId':category,'unitId':unit,'status':0,'salePrice':'0','purchasePrice':'0'})
        all_products.append(ident);return ident
    def inbound(p,w,q):
        ident=admin.create('stock-in',{'supplierId':supplier,'inTime':NOW,'items':[{'productId':p,'warehouseId':w,'productPrice':'0','count':str(q)}]})
        admin.approve('stock-in',ident);return ident
    def order(lines,client=admin):
        ident=client.create('sale-order',{'customerId':customer,'accountId':account,'orderTime':NOW,'discountPercent':'0','items':[{'productId':p,'count':str(q),'productPrice':'0','taxPercent':'0'} for p,q in lines]})
        client.approve('sale-order',ident);return client.bind(ident)['orderId']
    p=product('分仓');inbound(p,wa,'3.123456');inbound(p,wb,'6.000001')
    oid=order([(p,'7.000001')]);physical_before=balance(p,wa)[0]+balance(p,wb)[0]
    split_key='split'+RUN
    result=admin.allocate(oid,[wb,wa],key=split_key);check('split reserve outcome',result['outcome']=='ALLOCATED' and result['status']=='RESERVED',result)
    check('warehouse input order normalized for idempotency',second.allocate(oid,[wa,wb],key=split_key)==result)
    check('warehouse priority determines split',[(r['warehouseId'],r['heldQty']) for r in result['reservations']]==[(str(wa),'3.123456'),(str(wb),'3.876545')])
    check('reserve changes no physical inventory',balance(p,wa)[0]+balance(p,wb)[0]==physical_before)
    r0=result['reservations'][0]['id'];release_key='release'+RUN
    released=admin.release(oid,[(r0,'1.123456')],release_key)
    check('partial release returns WAIT_STOCK',released['status']=='WAIT_STOCK')
    check('release preserves physical',balance(p,wa)==(Decimal('3.123456'),Decimal('2.000000')))
    check('release normalized key replay stable',second.release(oid,[(r0,'1.123456')],release_key)==released)
    check('different release request conflicts',admin.release(oid,[(r0,'1')],release_key,ok=False)['code']==1080000005)
    check('too much release rejected',admin.release(oid,[(r0,'20')],ok=False)['code']==1080000012)
    check('duplicate release id rejected',admin.release(oid,[(r0,'1'),(r0,'1')],ok=False)['code']==1080000011)
    check('zero release rejected',admin.release(oid,[(r0,'0')],ok=False)['code']==1080000011)
    check('reallocation uses only reopened quantity',admin.allocate(oid,[wa,wb])['outcome']=='ALLOCATED')
    check('disabled candidate rejected',admin.allocate(oid,[disabled],ok=False)['code']==1080000010)
    check('duplicate candidate rejected',admin.allocate(oid,[wa,wa],ok=False)['code']==1080000011)
    check('missing/foreign candidate concealed',admin.allocate(oid,[9223372036854775807],ok=False)['code']==1080000010)
    view=admin.api('GET','/fulfillment/stock/get',params={'productId':p,'warehouseId':wa})
    check('H R A decimal string view',view['physical']=='3.123456' and view['reserved']=='3.123456' and view['available']=='0.000000',view)

    scarce=product('全量不足');other=product('充足商品');inbound(scarce,wa,'2');inbound(other,wa,'10')
    insufficient=order([(other,'5'),(scarce,'3')]);key='shortage'+RUN
    shortage=admin.allocate(insufficient,[wa],key=key)
    check('one missing SKU rejects whole plan normally',shortage['outcome']=='INSUFFICIENT_STOCK' and shortage['status']=='WAIT_STOCK' and not shortage['reservations'])
    check('no partial commitment survives',balance(other,wa)[1]==0 and balance(scarce,wa)[1]==0)
    inbound(scarce,wa,'1')
    check('same shortage command returns original result',second.allocate(insufficient,[wa],key=key)==shortage)
    check('new command can use replenished stock',admin.allocate(insufficient,[wa])['outcome']=='ALLOCATED')
    absent=product('缺行');missing_order=order([(absent,'1')]);missing=admin.allocate(missing_order,[wa])
    check('absent stock is zero and not created by allocation',missing['outcome']=='INSUFFICIENT_STOCK' and not sql('SELECT id FROM erp_stock WHERE product_id=%s',(absent,)))
    dup=product('重复商品');inbound(dup,wa,'5');duplicate_order=order([(dup,'4'),(dup,'4')]);duplicate_result=admin.allocate(duplicate_order,[wa])
    check('duplicate SKU cannot double use balance',duplicate_result['outcome']=='INSUFFICIENT_STOCK' and balance(dup,wa)[1]==0)

    single=product('单仓');inbound(single,wa,'3');inbound(single,wb,'10')
    single_order=order([(single,'7')]);single_result=admin.allocate(single_order,[wa,wb],'SINGLE_FIRST')
    check('single first selects lower-priority whole-order warehouse',len(single_result['reservations'])==1 and single_result['reservations'][0]['warehouseId']==str(wb))
    entire=single_result['reservations'][0]['id'];full_key='full'+RUN
    full_release=admin.release(single_order,[(entire,'7')],key=full_key)
    check('full release marks reservation inactive',sql('SELECT held_qty,released_qty,active_flag FROM ful_reservation WHERE id=%s',(entire,))[0]==(Decimal(0),Decimal(7),b'\x00'))
    check('release decimal representation normalized',second.release(single_order,[(entire,'7.000000')],key=full_key)==full_release)
    check('different key cannot release already released stock',admin.release(single_order,[(entire,'7')],ok=False)['code']==1080000012)
    check('reallocate after full release succeeds',admin.allocate(single_order,[wa,wb],'SINGLE_FIRST')['outcome']=='ALLOCATED')
    fallback=product('回退拆分');inbound(fallback,wa,'3');inbound(fallback,wb,'4')
    fallback_result=admin.allocate(order([(fallback,'7')]),[wa,wb],'SINGLE_FIRST')
    check('single first deterministic split fallback',len(fallback_result['reservations'])==2)

    race_product=product('竞争');inbound(race_product,wa,'10')
    competitors=[order([(race_product,'3')]) for _ in range(8)];barrier=threading.Barrier(8)
    def compete(index):
        client=M2Client(48080 if index%2==0 else 48082);client.s.headers.update(admin.s.headers);barrier.wait()
        return client.allocate(competitors[index],[wa])
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:race=list(pool.map(compete,range(8)))
    check('two JVMs limited-stock race admits exactly three orders',sum(r['outcome']=='ALLOCATED' for r in race)==3 and balance(race_product,wa)==(Decimal('10'),Decimal('9')),race)

    same_product=product('幂等');inbound(same_product,wa,'4');same_order=order([(same_product,'4')]);barrier=threading.Barrier(6);same_key='same'+RUN
    def same(index):
        client=M2Client(48080 if index%2==0 else 48082);client.s.headers.update(admin.s.headers);barrier.wait();return client.allocate(same_order,[wa],key=same_key)
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:same_results=list(pool.map(same,range(6)))
    check('T04 both JVMs return one saved allocation',all(r==same_results[0] for r in same_results) and balance(same_product,wa)[1]==4)
    check('one reserve and one command',sql('SELECT COUNT(*) FROM ful_reservation WHERE order_id=%s',(same_order,))[0][0]==1 and sql("SELECT COUNT(*) FROM ful_command_record WHERE command_type='ALLOCATE' AND idempotency_key=%s",(same_key,))[0][0]==1)
    check('T05 same key different strategy conflicts',second.allocate(same_order,[wa],'SINGLE_FIRST',same_key,ok=False)['code']==1080000005)

    first=product('首次建行');start=threading.Barrier(2)
    in_docs=[admin.create('stock-in',{'supplierId':supplier,'inTime':NOW,'items':[{'productId':first,'warehouseId':wa,'count':'0.000001','productPrice':'0'}]}) for _ in range(2)]
    def first_insert(index):
        client=M2Client(48080 if index==0 else 48082);client.s.headers.update(admin.s.headers);start.wait();return client.approve('stock-in',in_docs[index])
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(first_insert,range(2)))
    check('T28 concurrent first insert creates one exact balance',balance(first,wa)==(Decimal('0.000002'),Decimal(0)) and sql('SELECT COUNT(*) FROM erp_stock WHERE product_id=%s',(first,))[0][0]==1)

    large=product('大数精度');inbound(large,wa,'9007199254740992.000001');inbound(large,wb,'0.000001')
    total=admin.api('GET','/erp/stock/get-count',params={'productId':large})
    check('T29 BigDecimal SUM beyond double precision',Decimal(str(total))==Decimal('9007199254740992.000002'),str(total))
    large_order=order([(large,'9007199254740992.000001')]);large_result=admin.allocate(large_order,[wa])
    check('T29 exact large allocation string',large_result['reservations'][0]['heldQty']=='9007199254740992.000001')
    maximum=product('最大合法数量');inbound(maximum,wa,'999999999999999999.999999')
    max_result=admin.allocate(order([(maximum,'999999999999999999.999999')]),[wa])
    check('T29 maximum DECIMAL24_6 remains exact',max_result['reservations'][0]['heldQty']=='999999999999999999.999999' and balance(maximum,wa)[0]==Decimal('999999999999999999.999999'))

    # Force a lock timeout, then release the external test lock. The first attempt
    # must roll back its command row before a whole-transaction retry can succeed.
    retry_product=product('锁重试');inbound(retry_product,wa,'1');retry_order=order([(retry_product,'1')]);retry_key='retry'+RUN
    retry_log=ROOT/'.local'/os.getenv('M2_SECONDARY_LOG','m2-secondary-out.log')
    before_retry=retry_log.read_text(encoding='utf-8',errors='replace').count('Retry entire database command')
    stock_id=sql('SELECT id FROM erp_stock WHERE tenant_id=1 AND product_id=%s AND warehouse_id=%s',(retry_product,wa))[0][0]
    with db() as hold:
        hold.begin()
        with hold.cursor() as cur:cur.execute('SELECT id FROM erp_stock WHERE id=%s FOR UPDATE',(stock_id,))
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            waiting=pool.submit(second.allocate,retry_order,[wa],'PRIORITY_SPLIT',retry_key)
            try:time.sleep(4.2)
            finally:hold.rollback()
            retried=waiting.result()
    check('real lock timeout retries whole transaction',retried['outcome']=='ALLOCATED' and balance(retry_product,wa)[1]==1)
    retry_lines=[line for line in retry_log.read_text(encoding='utf-8',errors='replace').splitlines() if 'Retry entire database command' in line]
    check('actual server retry observed after forced lock timeout',len(retry_lines)>before_retry,retry_lines[before_retry:])
    E['forced_retry_evidence']=retry_lines[before_retry:]
    check('retry has no orphan command or reservation',sql('SELECT COUNT(*) FROM ful_command_record WHERE idempotency_key=%s',(retry_key,))[0][0]==1 and sql('SELECT COUNT(*) FROM ful_reservation WHERE order_id=%s',(retry_order,))[0][0]==1)

    # DB final defense, with no fixture mutation committed.
    with db() as c:
        c.begin()
        try:
            with c.cursor() as cur:
                for label,statement,args in [
                    ('H cannot fall below R','UPDATE erp_stock SET `count`=ful_reserved_count-1 WHERE product_id=%s AND warehouse_id=%s',(same_product,wa)),
                    ('R cannot be negative','UPDATE erp_stock SET ful_reserved_count=-1 WHERE product_id=%s AND warehouse_id=%s',(same_product,wa)),
                    ('stock cannot be soft deleted','UPDATE erp_stock SET deleted=1 WHERE product_id=%s AND warehouse_id=%s',(same_product,wa))]:
                    try:cur.execute(statement,args);check(label,False)
                    except Exception as error:check(label,getattr(error,'args',[None])[0]==3819,str(error))
        finally:c.rollback()
    invariants(all_products)
    E['ids'].update(unit=unit,category=category,customer=customer,supplier=supplier,account=account,warehouse_a=wa,warehouse_b=wb,products=all_products,split_order=oid,split_product=p,split_reservation=r0,hold_order=same_order)
    E['result']='passed'
if __name__=='__main__':
    try:main()
    except Exception as exc:E['result']='failed';E['error']=str(exc);raise
    finally:
        (ROOT/'../学习资料/10-验收证据'/os.getenv('M2_EVIDENCE','M2-acceptance.json')).write_text(json.dumps(E,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
        print('M2',E.get('result'),len(E['checks']),'checks')
