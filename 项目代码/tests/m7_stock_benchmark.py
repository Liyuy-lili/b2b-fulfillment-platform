"""Actual HTTP stock competition, setup excluded, exact invariants each round.
Use --prepare while other suites run, then no argument after correctness gates.
"""
import hashlib,json,os,sys,time,uuid
from datetime import datetime,timezone
from collections import Counter
from decimal import Decimal
import requests,psutil
import m7_support as h
from m7_perf_tools import Sample,parallel,root_sql,cpu_model
PREP='--prepare' in sys.argv
DB='fulfillment_m7_stock_'+datetime.now().strftime('%Y%m%d_%H%M%S') if PREP else h.load('M7.3-stock-prepare.json')['database']
E={'run_at':datetime.now(timezone.utc).isoformat(),'database':DB,'artifact_sha256':h.sha(h.JAR),'checks':[],'rounds':[],'origin':'Every master, inbound, source order, approval, binding, allocation and release via actual HTTP. SQL reads only after migrations.'}
rt=h.Runtime(DB,11);q=lambda s,a=():h.sql(DB,s,a)
def check(name,ok,detail=None):
    E['checks'].append(dict(name=name,passed=bool(ok),detail=detail));print(('PASS ' if ok else 'FAIL ')+name,flush=True);assert ok,name
def status():return dict(root_sql("SHOW GLOBAL STATUS WHERE Variable_name IN ('Innodb_row_lock_waits','Innodb_row_lock_time','Innodb_deadlocks')"))
try:
    if PREP:E['commands']=h.initialize(DB)
    else:check('all correctness suites passed before timed experiment',all(h.load('M7.2-'+c+'-run.json')['result']=='passed' for c in ['core','expiry','returns','reconcile','message','filefoundation','file']))
    process=rt.start(48085,'stock-prepare' if PREP else 'stock-benchmark');c=h.Client(48085).login()
    if PREP:
        def create(kind,body):return c.api('POST','/erp/'+kind+'/create',body)
        unit=create('product-unit',{'name':'M7库存件','status':0});cat=create('product-category',{'name':'M7库存','code':'M7STOCK','parentId':0,'sort':1,'status':0});customer=create('customer',{'name':'M7库存客户','sort':1,'status':0});account=create('account',{'name':'M7库存账户','no':'M7STOCK','sort':1,'status':0});supplier=create('supplier',{'name':'M7库存供应商','sort':1,'status':0});w=create('warehouse',{'name':'M7争抢仓','sort':1,'status':0,'warehousePrice':'0','truckagePrice':'0'});p=create('product',{'name':'M7争抢商品','barCode':'M7STOCK','unitId':unit,'categoryId':cat,'status':0,'salePrice':'0'})
        inbound=create('stock-in',{'supplierId':supplier,'inTime':datetime.now().isoformat(timespec='seconds'),'items':[{'productId':p,'warehouseId':w,'count':'32','productPrice':'0'}]});c.api('PUT','/erp/stock-in/update-status',params={'id':inbound,'status':20});orders=[]
        for n in range(512):
            source=create('sale-order',{'customerId':customer,'accountId':account,'orderTime':datetime.now().isoformat(timespec='seconds'),'items':[{'productId':p,'count':'1','productPrice':'0','taxPercent':'0'}]});c.api('PUT','/erp/sale-order/update-status',params={'id':source,'status':20});oid=c.api('POST','/fulfillment/order/bind',{'erpOrderId':str(source)},key='m7-stock-bind-'+str(n))['orderId'];orders.append(oid)
            if (n+1)%64==0:print('Prepared orders',n+1,flush=True)
        E['fixtures']={'product':p,'warehouse':w,'orders':orders,'physical':32};check('512 actual unallocated order fixtures',len(orders)==512 and q('SELECT COUNT(*) FROM ful_order')[0][0]==512)
    else:
        fixtures=h.load('M7.3-stock-prepare.json')['fixtures'];p=fixtures['product'];w=fixtures['warehouse'];orders=fixtures['orders'];E['fixtures']=fixtures;headers=dict(c.s.headers)
        E['environment']={'logical_processors':os.cpu_count(),'ram_bytes':psutil.virtual_memory().total,'jvm_args':['-Xms128m','-Xmx768m'],'instances':1,'druid_max_active':12,'mysql':q('SELECT VERSION(),@@innodb_buffer_pool_size,@@transaction_isolation'),'warmup':'First eight orders allocate/release outside measurements','mix':'100% same SKU/warehouse allocation, 64 orders compete H32; business shortage is not transport error','concurrency':[1,4,8,16],'repeats':2,'setup_and_release_excluded':True,'lock_counters':'Global MySQL deltas; main idle, shared service, not strictly process attributable'}
        E['environment'].update(cpu_model=cpu_model(),physical_cores=psutil.cpu_count(logical=False),mysql_tuple_columns=['version','innodb_buffer_pool_size','probe_connection_isolation_not_application'],application_write_isolation='READ_COMMITTED; startup verified',client='A real requests.Session per allocation, connection setup included; login excluded',cpu_metric='100 percent equals one fully used CPU core')
        def allocate(oid):
            session=requests.Session();session.headers.update(headers)
            try:
                response=session.post(c.base+'/fulfillment/order/allocate',json={'orderId':oid,'warehouseIds':[str(w)],'strategy':'PRIORITY_SPLIT','holdSeconds':900},headers={'Idempotency-Key':'m7-stock-allocate-'+str(oid)+'-'+uuid.uuid4().hex},timeout=90);response.raise_for_status();body=response.json();assert body['code']==0,body;result=body['data'];assert result['outcome'] in ['ALLOCATED','INSUFFICIENT_STOCK'],result;return result
            finally:session.close()
        def release(result):
            if result['outcome']=='ALLOCATED':c.api('POST','/fulfillment/order/release',{'orderId':result['orderId'],'items':[{'reservationId':r['id'],'quantity':r['heldQty']} for r in result['reservations']],'reason':'M7 benchmark release after measured phase'},key=uuid.uuid4().hex)
        def invariant(expected_r):
            physical,reserved=q('SELECT `count`,ful_reserved_count FROM erp_stock WHERE product_id=%s AND warehouse_id=%s',(p,w))[0];held=q('SELECT COALESCE(SUM(held_qty),0) FROM ful_reservation WHERE product_id=%s AND warehouse_id=%s',(p,w))[0][0];delta=q('SELECT COALESCE(SUM(held_delta),0) FROM ful_stock_ledger WHERE product_id=%s AND warehouse_id=%s',(p,w))[0][0];physical_ledger=q('SELECT COALESCE(SUM(`count`),0) FROM erp_stock_record WHERE product_id=%s AND warehouse_id=%s',(p,w))[0][0]
            check('H32 R'+str(expected_r)+' and both ledgers exact',physical==physical_ledger==32 and reserved==held==delta==expected_r and 0<=reserved<=physical)
            check('all item quantity identities',q('SELECT COUNT(*) FROM ful_order_item WHERE ordered_qty<>open_qty+reserved_qty+shipped_qty+cancelled_qty OR returned_qty>shipped_qty')[0][0]==0)
        for oid in orders[:8]:release(allocate(oid))
        invariant(0)
        for repeat in range(2):
            for index,concurrency in enumerate([1,4,8,16]):
                batch=orders[(repeat*4+index)*64:(repeat*4+index+1)*64];before=status()
                with Sample(process.pid) as resource:raw,stats=parallel(allocate,batch,concurrency)
                after=status();outcomes=Counter(r['result']['outcome'] for r in raw if r['ok']);E['rounds'].append({'repeat':repeat+1,'concurrency':concurrency,'summary':stats,'outcomes':dict(outcomes),'requests':raw,'resources':resource.result,'mysql_global_delta':{k:int(after[k])-int(before[k]) for k in before}})
                check('64 requests exactly32 success32 shortage c'+str(concurrency),stats['errors']==0 and outcomes=={'ALLOCATED':32,'INSUFFICIENT_STOCK':32},stats);invariant(32)
                for row in raw:release(row['result'])
                invariant(0);h.save('M7.3-stock.json',E)
        report=c.api('POST','/fulfillment/reconcile/run',{'scope':'TENANT'},key='m7-stock-final-reconcile');check('full final reconciliation no differences',report['differenceCount']==0,report);E['reconcile']=report
    E['result']='passed'
except Exception as error:E.update(result='failed',error=str(error));raise
finally:
    E['owned_stopped']=rt.close();h.save('M7.3-stock-prepare.json' if PREP else 'M7.3-stock.json',E)
    if E.get('result')=='failed':h.save('M7.3-stock-failed-'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.json',E)
