"""T13 real HTTP verification of all enabled ERP stock writers and reversals.
Business fixtures use APIs. Assertions read MySQL facts and original stock ledgers.
"""
import concurrent.futures,json,os,threading,uuid,time
from datetime import datetime,timezone
from decimal import Decimal
from m2_acceptance import M2Client,balance
from m1_acceptance import ROOT,sql,db

E={'date':'2026-10-18','run_at':datetime.now(timezone.utc).isoformat(),'checks':[],'cases':[]}
RUN='M2L'+uuid.uuid4().hex[:7];NOW=datetime.now().isoformat(timespec='seconds')
def check(name,ok,detail=None):
    E['checks'].append({'name':name,'passed':bool(ok),'detail':detail})
    if not ok:raise AssertionError(name+': '+str(detail))
def main():
    admin=M2Client().login();second=M2Client(48082).login()
    f=json.loads((ROOT/'../学习资料/10-验收证据'/os.getenv('M2_BASE_EVIDENCE','M2-acceptance.json')).read_text(encoding='utf-8'))['ids']
    wa,wb=f['warehouse_a'],f['warehouse_b'];customer,supplier,account=f['customer'],f['supplier'],f['account']
    products=[]
    def product(name):
        p=admin.create('product',{'name':RUN+name,'barCode':RUN+name,'categoryId':f['category'],'unitId':f['unit'],'status':0,'purchasePrice':'0','salePrice':'0'});products.append(p);return p
    def item(p,w,q):return {'productId':p,'productUnitId':f['unit'],'warehouseId':w,'productPrice':'0','count':str(q),'taxPercent':'0'}
    def stock_in(p,w,q):
        ident=admin.create('stock-in',{'supplierId':supplier,'inTime':NOW,'items':[item(p,w,q)]});admin.approve('stock-in',ident);return ident
    def sale(p,q):
        ident=admin.create('sale-order',{'customerId':customer,'accountId':account,'orderTime':NOW,'discountPercent':'0','items':[item(p,wa,q)]});admin.approve('sale-order',ident)
        source_item=admin.api('GET','/erp/sale-order/get',params={'id':ident})['items'][0]['id'];return ident,source_item
    def reserve(p,q='8'):
        source,_=sale(p,q);ful=admin.bind(source)['orderId'];result=admin.allocate(ful,[wa]);check('fixture reservation succeeds',result['outcome']=='ALLOCATED');return ful
    def purchase(p,q='10'):
        po=admin.create('purchase-order',{'supplierId':supplier,'accountId':account,'orderTime':NOW,'discountPercent':'0','items':[item(p,wa,q)]});admin.approve('purchase-order',po)
        pi=admin.api('GET','/erp/purchase-order/get',params={'id':po})['items'][0]['id']
        incoming=admin.create('purchase-in',{'orderId':po,'accountId':account,'inTime':NOW,'discountPercent':'0','otherPrice':'0','items':[dict(item(p,wa,q),orderItemId=pi)]});admin.approve('purchase-in',incoming)
        return po,pi,incoming
    def state(p):
        return (sql('SELECT warehouse_id,`count`,ful_reserved_count FROM erp_stock WHERE tenant_id=1 AND product_id=%s ORDER BY warehouse_id',(p,)),sql('SELECT COUNT(*) FROM erp_stock_record WHERE tenant_id=1 AND product_id=%s',(p,))[0][0])
    def reject(kind,ident,p,reverse=False):
        before=state(p);result=admin.approve(kind,ident,10 if reverse else 20,ok=False)
        check(kind+(' reversal' if reverse else ' reduction')+' rejects unavailable stock',result['code']==1030404000,result)
        check(kind+' failure rolls back all inventory and ledgers',state(p)==before)
        detail=admin.api('GET','/erp/'+kind+'/get',params={'id':ident})
        check(kind+' failure restores document status',detail['status']==(20 if reverse else 10))
        E['cases'].append({'kind':kind,'id':ident,'product':p,'reverse':reverse,'code':result['code']})

    # Four ordinary reductions and an inbound reversal share H=10, R=8, A=2.
    p=product('普通减少');incoming=stock_in(p,wa,'10');reserve(p)
    out=admin.create('stock-out',{'customerId':customer,'outTime':NOW,'items':[item(p,wa,'3')]});reject('stock-out',out,p)
    move=admin.create('stock-move',{'customerId':customer,'moveTime':NOW,'items':[dict(item(p,wa,'3'),fromWarehouseId=wa,toWarehouseId=wb)]});reject('stock-move',move,p)
    loss=admin.create('stock-check',{'checkTime':NOW,'items':[dict(item(p,wa,'-3'),stockCount='10',actualCount='7')]});reject('stock-check',loss,p)
    so,si=sale(p,'3');sales_out=admin.create('sale-out',{'orderId':so,'accountId':account,'outTime':NOW,'discountPercent':'0','otherPrice':'0','items':[dict(item(p,wa,'3'),orderItemId=si)]});reject('sale-out',sales_out,p)
    reject('stock-in',incoming,p,True)
    # Equal to availability is allowed; a full consumption must preserve H==R.
    allowed=admin.create('stock-out',{'customerId':customer,'outTime':NOW,'items':[item(p,wa,'2')]});admin.approve('stock-out',allowed)
    check('ordinary out can consume exactly available stock',balance(p,wa)==(Decimal('8'),Decimal('8')))
    admin.approve('stock-out',allowed,10);check('out reversal increases physical only',balance(p,wa)==(Decimal('10'),Decimal('8')))
    # A loss reversal increases H. It remains legal while preoccupied.
    gain_back=admin.create('stock-check',{'checkTime':NOW,'items':[dict(item(p,wa,'-1'),stockCount='10',actualCount='9')]});admin.approve('stock-check',gain_back);admin.approve('stock-check',gain_back,10)
    check('loss reversal restores H without changing R',balance(p,wa)==(Decimal('10'),Decimal('8')))

    purchase_product=product('采购减少');po,pi,pin=purchase(purchase_product);reserve(purchase_product)
    returned=admin.create('purchase-return',{'orderId':po,'accountId':account,'returnTime':NOW,'discountPercent':'0','otherPrice':'0','items':[dict(item(purchase_product,wa,'3'),orderItemId=pi)]});reject('purchase-return',returned,purchase_product)
    reject('purchase-in',pin,purchase_product,True)
    # Purchase-return reversal adds H; use a separately approved small return.
    small_return=admin.create('purchase-return',{'orderId':po,'accountId':account,'returnTime':NOW,'discountPercent':'0','otherPrice':'0','items':[dict(item(purchase_product,wa,'1'),orderItemId=pi)]});admin.approve('purchase-return',small_return);admin.approve('purchase-return',small_return,10)
    check('purchase return reversal restores physical',balance(purchase_product,wa)==(Decimal('10'),Decimal('8')))

    sale_product=product('销售退货撤销');stock_in(sale_product,wa,'10');so,si=sale(sale_product,'3')
    sout=admin.create('sale-out',{'orderId':so,'accountId':account,'outTime':NOW,'discountPercent':'0','otherPrice':'0','items':[dict(item(sale_product,wa,'3'),orderItemId=si)]});admin.approve('sale-out',sout)
    sreturn=admin.create('sale-return',{'orderId':so,'accountId':account,'returnTime':NOW,'discountPercent':'0','otherPrice':'0','items':[dict(item(sale_product,wa,'3'),orderItemId=si)]});admin.approve('sale-return',sreturn);reserve(sale_product)
    reject('sale-return',sreturn,sale_product,True)
    admin.approve('sale-out',sout,10);check('unmanaged sale out reversal adds physical only',balance(sale_product,wa)==(Decimal('13'),Decimal('8')))

    check_product=product('盘盈撤销');stock_in(check_product,wa,'7')
    gain=admin.create('stock-check',{'checkTime':NOW,'items':[dict(item(check_product,wa,'3'),stockCount='7',actualCount='10')]});admin.approve('stock-check',gain);reserve(check_product)
    reject('stock-check',gain,check_product,True)

    move_product=product('调拨撤销');stock_in(move_product,wb,'10')
    completed_move=admin.create('stock-move',{'customerId':customer,'moveTime':NOW,'items':[dict(item(move_product,wb,'10'),fromWarehouseId=wb,toWarehouseId=wa)]});admin.approve('stock-move',completed_move);reserve(move_product)
    reject('stock-move',completed_move,move_product,True)
    check('failed move reversal keeps destination and source atomic',balance(move_product,wa)==(Decimal('10'),Decimal('8')) and balance(move_product,wb)==(Decimal(0),Decimal(0)))

    free=product('先写后回滚');stock_in(free,wa,'10');before_free=state(free)
    multi=admin.create('stock-out',{'customerId':customer,'outTime':NOW,'items':[item(free,wa,'2'),item(p,wa,'3')]})
    reject('stock-out',multi,p)
    check('later-line failure rolls back earlier product and ledger',state(free)==before_free)

    moving=product('反向并发');stock_in(moving,wa,'10');stock_in(moving,wb,'10')
    a=admin.create('stock-move',{'customerId':customer,'moveTime':NOW,'items':[dict(item(moving,wa,'1'),fromWarehouseId=wa,toWarehouseId=wb)]})
    b=admin.create('stock-move',{'customerId':customer,'moveTime':NOW,'items':[dict(item(moving,wb,'1'),fromWarehouseId=wb,toWarehouseId=wa)]})
    start=threading.Barrier(2)
    def move_race(pair):
        client,ident=pair;start.wait();return client.approve('stock-move',ident)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(move_race,[(admin,a),(second,b)]))
    check('opposite moves across two JVMs both finish consistently',balance(moving,wa)==(Decimal('10'),Decimal(0)) and balance(moving,wb)==(Decimal('10'),Decimal(0)))
    # The old ERP transactional proxy must restart status CAS + stock + ledger,
    # not retry only the failed SQL after the transaction has rolled back.
    retry_product=product('旧入口重试');stock_in(retry_product,wa,'10')
    retry_out=admin.create('stock-out',{'customerId':customer,'outTime':NOW,'items':[item(retry_product,wa,'2')]})
    retry_log=ROOT/'.local/backend-out.log';before_retry=retry_log.read_text(encoding='utf-8',errors='replace').count('Retry entire database command')
    stock_id=sql('SELECT id FROM erp_stock WHERE tenant_id=1 AND product_id=%s AND warehouse_id=%s',(retry_product,wa))[0][0]
    with db() as hold:
        hold.begin()
        with hold.cursor() as cur:cur.execute('SELECT id FROM erp_stock WHERE id=%s FOR UPDATE',(stock_id,))
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            operation=pool.submit(admin.approve,'stock-out',retry_out)
            try:time.sleep(4.2)
            finally:hold.rollback()
            operation.result()
    retry_lines=[line for line in retry_log.read_text(encoding='utf-8',errors='replace').splitlines() if 'Retry entire database command' in line]
    check('legacy whole transaction actually retried',len(retry_lines)>before_retry,retry_lines[before_retry:])
    check('legacy retry commits one deduction and ledger',balance(retry_product,wa)==(Decimal('8'),Decimal(0)) and sql('SELECT COUNT(*) FROM erp_stock_record WHERE product_id=%s',(retry_product,))[0][0]==2)
    E['forced_retry_evidence']=retry_lines[before_retry:]

    E['allocation_legacy_races']=[]
    for index in range(4):
        shared=product('新旧竞争'+str(index));stock_in(shared,wa,'10');source,_=sale(shared,'8');ful=admin.bind(source)['orderId']
        outbound=admin.create('stock-out',{'customerId':customer,'outTime':NOW,'items':[item(shared,wa,'3')]});gate=threading.Barrier(2)
        def allocating():gate.wait();return admin.allocate(ful,[wa])
        def reducing():gate.wait();return second.approve('stock-out',outbound,ok=False)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            a=pool.submit(allocating);b=pool.submit(reducing);allocated,old=a.result(),b.result()
        valid=(allocated['outcome']=='ALLOCATED' and old['code']!=0 and balance(shared,wa)==(Decimal('10'),Decimal('8'))) or (allocated['outcome']=='INSUFFICIENT_STOCK' and old['code']==0 and balance(shared,wa)==(Decimal('7'),Decimal(0)))
        check('allocate and legacy reduce serialize across JVMs '+str(index),valid,{'allocation':allocated['outcome'],'legacy_code':old['code']})
        E['allocation_legacy_races'].append({'product':shared,'allocation':allocated['outcome'],'legacy_code':old['code']})
    # A negative outgoing quantity must never mint physical inventory. Keep old
    # draft/history compatibility, but reject invalid source quantities before any approval effect.
    invalid_sale,invalid_si=sale(p,'1')
    bad_sale_items=[dict(item(p,wa,'-1'),orderItemId=invalid_si)]
    invalid_bodies=[
        ('stock-in',{'supplierId':supplier,'inTime':NOW,'items':[item(p,wa,'-1')]}),
        ('stock-out',{'customerId':customer,'outTime':NOW,'items':[item(p,wa,'-1')]}),
        ('stock-move',{'customerId':customer,'moveTime':NOW,'items':[dict(item(p,wa,'-1'),fromWarehouseId=wa,toWarehouseId=wb)]}),
        ('stock-check',{'checkTime':NOW,'items':[dict(item(p,wa,'-3'),stockCount='10',actualCount='9')]}),
        ('sale-out',{'orderId':invalid_sale,'accountId':account,'outTime':NOW,'discountPercent':'0','otherPrice':'0','items':bad_sale_items}),
        ('sale-return',{'orderId':invalid_sale,'accountId':account,'returnTime':NOW,'discountPercent':'0','otherPrice':'0','items':bad_sale_items}),
        ('purchase-return',{'orderId':po,'accountId':account,'returnTime':NOW,'discountPercent':'0','otherPrice':'0','items':[dict(item(purchase_product,wa,'-1'),orderItemId=pi)]}),
        ('purchase-in',{'orderId':po,'accountId':account,'inTime':NOW,'discountPercent':'0','otherPrice':'0','items':[dict(item(purchase_product,wa,'-1'),orderItemId=pi)]})]
    for kind,body in invalid_bodies:
        target=purchase_product if kind.startswith('purchase-') else p
        before=state(target);created=admin.api('POST','/erp/'+kind+'/create',body,ok=False)
        if created['code']==0:result=admin.approve(kind,created['data'],ok=False)
        else:result=created
        check(kind+' invalid natural quantity or count delta rejected',result['code'] in (400,1030404002),result)
        check(kind+' invalid quantity creates no physical effect',state(target)==before)
    for p in products:
        for warehouse,h,r in sql('SELECT warehouse_id,`count`,ful_reserved_count FROM erp_stock WHERE tenant_id=1 AND product_id=%s',(p,)):
            held=sql('SELECT COALESCE(SUM(held_qty),0) FROM ful_reservation WHERE tenant_id=1 AND product_id=%s AND warehouse_id=%s',(p,warehouse))[0][0]
            reserve_ledger=sql('SELECT COALESCE(SUM(held_delta),0) FROM ful_stock_ledger WHERE tenant_id=1 AND product_id=%s AND warehouse_id=%s',(p,warehouse))[0][0]
            check('legacy paths preserve held commitment',0<=r<=h and r==held==reserve_ledger)
            running=Decimal(0)
            for delta,after in sql('SELECT `count`,total_count FROM erp_stock_record WHERE tenant_id=1 AND product_id=%s AND warehouse_id=%s ORDER BY id',(p,warehouse)):
                running+=delta;check('legacy current-read running ledger',running==after)
            check('legacy physical total equals ledger',running==h)
    E['products']=products;E['result']='passed'
if __name__=='__main__':
    try:main()
    except Exception as exc:E['result']='failed';E['error']=str(exc);raise
    finally:
        (ROOT/'../学习资料/10-验收证据'/os.getenv('M2_LEGACY_EVIDENCE','M2-legacy-inventory.json')).write_text(json.dumps(E,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
        print('M2 legacy',E.get('result'),len(E['checks']),'checks')
