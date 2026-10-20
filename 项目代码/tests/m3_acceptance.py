"""M3 real HTTP/MySQL checks: two JVMs plus isolated fail-after-ERP profile."""
import concurrent.futures,hashlib,hmac,json,os,time,uuid
from datetime import datetime,timezone
from decimal import Decimal
import requests
from m2_acceptance import M2Client,balance
from m1_acceptance import ROOT,sql

E={'run_at':datetime.now(timezone.utc).isoformat(),'checks':[],'ids':{}}
RUN='M3'+uuid.uuid4().hex[:8];NOW=datetime.now().isoformat(timespec='seconds')
class M3Client(M2Client):
    def ship(self,order,warehouse,lines,key=None,ok=True):
        return self.api('POST','/fulfillment/shipment/confirm',{'orderId':str(order),'warehouseId':str(warehouse),'items':[{'id':str(r),'quantity':str(q)} for r,q in lines],'carrierCode':'SIMULATED','trackingNo':'TRACK-'+str(order)},ok=ok,headers={'Idempotency-Key':key or uuid.uuid4().hex})
    def cancel(self,order,lines,key=None,ok=True):
        return self.api('POST','/fulfillment/order/cancel',{'orderId':str(order),'items':[{'id':str(i),'quantity':str(q)} for i,q in lines],'reason':'M3 customer change'},ok=ok,headers={'Idempotency-Key':key or uuid.uuid4().hex})
def check(name,ok,detail=None):
    E['checks'].append({'name':name,'passed':bool(ok),'detail':detail})
    if not ok:raise AssertionError(name+': '+str(detail))
def quantities(order):return sql('SELECT ordered_qty,open_qty,reserved_qty,shipped_qty,cancelled_qty FROM ful_order_item WHERE order_id=%s ORDER BY id',(order,))
def invariant(products):
    for p in products:
        for warehouse,h,r in sql('SELECT warehouse_id,`count`,ful_reserved_count FROM erp_stock WHERE tenant_id=1 AND product_id=%s',(p,)):
            held=sql('SELECT COALESCE(SUM(held_qty),0) FROM ful_reservation WHERE tenant_id=1 AND product_id=%s AND warehouse_id=%s',(p,warehouse))[0][0]
            delta=sql('SELECT COALESCE(SUM(held_delta),0) FROM ful_stock_ledger WHERE tenant_id=1 AND product_id=%s AND warehouse_id=%s',(p,warehouse))[0][0]
            physical=sql('SELECT COALESCE(SUM(`count`),0) FROM erp_stock_record WHERE tenant_id=1 AND product_id=%s AND warehouse_id=%s',(p,warehouse))[0][0]
            check('H R held and both ledgers match',Decimal(0)<=r<=h and r==held==delta and h==physical,{'product':p,'warehouse':warehouse,'H':h,'R':r})
            running=Decimal(0)
            for q,after in sql('SELECT held_delta,reserved_after FROM ful_stock_ledger WHERE tenant_id=1 AND product_id=%s AND warehouse_id=%s ORDER BY id',(p,warehouse)):
                running+=q;check('reservation ledger balance is exact',running==after)
    for order,ordered,opened,reserved,shipped,cancelled in sql("SELECT order_id,ordered_qty,open_qty,reserved_qty,shipped_qty,cancelled_qty FROM ful_order_item WHERE product_id IN ("+','.join(['%s']*len(products))+")",products):
        held=sql('SELECT COALESCE(SUM(held_qty),0) FROM ful_reservation WHERE order_id=%s AND order_item_id IN (SELECT id FROM ful_order_item WHERE order_id=%s AND product_id IN ('+','.join(['%s']*len(products))+'))',(order,order,*products))[0][0]
        check('order quantity identity',ordered==opened+reserved+shipped+cancelled and reserved==held)

def callback(shipment,kind='DELIVERED',event=None,occurred=None,stamp=None,raw=None,signature=None,integration='local-demo',header_event=None,tenant=None,port=48080):
    event=event or uuid.uuid4().hex;stamp=stamp or str(int(time.time()));occurred=occurred or datetime.now(timezone.utc).isoformat()
    body={'provider':'SIMULATED','eventId':event,'shipmentNo':shipment,'eventType':kind,'occurredAt':occurred}
    raw=raw or json.dumps(body,separators=(',',':')).encode()
    secret=os.environ.get('LOGISTICS_SECRET','local-logistics-demo-secret-change-before-sharing')
    signature=signature or hmac.new(secret.encode(),stamp.encode()+b'\n'+(header_event or event).encode()+b'\n'+raw,hashlib.sha256).hexdigest()
    headers={'Content-Type':'application/json','X-Logistics-Timestamp':stamp,'X-Logistics-Event-Id':header_event or event,'X-Logistics-Signature':signature}
    if tenant is not None:headers['tenant-id']=str(tenant)
    response=requests.post(f'http://127.0.0.1:{port}/app-api/fulfillment/logistics/callback/{integration}',data=raw,headers=headers,timeout=30)
    return response.json(),raw

def main():
    admin=M3Client().login();second=M3Client(48082).login();fault=M3Client(48083).login()
    unit=admin.create('product-unit',{'name':RUN+'件','status':0})
    category=admin.create('product-category',{'name':RUN,'code':RUN,'parentId':0,'sort':1,'status':0})
    customer=admin.create('customer',{'name':RUN+'客户','status':0,'sort':1})
    supplier=admin.create('supplier',{'name':RUN+'供应商','status':0,'sort':1})
    account=admin.create('account',{'name':RUN+'账户','no':RUN,'status':0,'sort':1})
    wa=admin.create('warehouse',{'name':RUN+'优先仓','sort':1,'status':0,'warehousePrice':'0','truckagePrice':'0'})
    wb=admin.create('warehouse',{'name':RUN+'次选仓','sort':2,'status':0,'warehousePrice':'0','truckagePrice':'0'})
    products=[]
    def product(label):
        p=admin.create('product',{'name':RUN+label,'barCode':RUN+label,'categoryId':category,'unitId':unit,'status':0,'salePrice':'2.345678','purchasePrice':'0'})
        products.append(p);return p
    def inbound(p,w,q):
        ident=admin.create('stock-in',{'supplierId':supplier,'inTime':NOW,'items':[{'productId':p,'warehouseId':w,'productPrice':'0','count':str(q)}]});admin.approve('stock-in',ident)
    def order(p,q):
        source=admin.create('sale-order',{'customerId':customer,'accountId':account,'orderTime':NOW,'discountPercent':'5','items':[{'productId':p,'count':str(q),'productPrice':'2.345678','taxPercent':'13'}]})
        admin.approve('sale-order',source);oid=admin.bind(source)['orderId'];item=admin.api('GET','/fulfillment/order/get',params={'id':oid})['items'][0]['id'];return source,oid,item
    # Start a real 60-second expiry clock; other tests run while it ages.
    ep=product('到期');inbound(ep,wa,'2');_,expiry,expiry_item=order(ep,'2')
    expired=admin.api('POST','/fulfillment/order/allocate',{'orderId':expiry,'warehouseIds':[str(wa)],'strategy':'PRIORITY_SPLIT','holdSeconds':60},headers={'Idempotency-Key':uuid.uuid4().hex})['reservations'][0]
    expiry_deadline=datetime.fromisoformat(expired['expireAt']).timestamp()

    p=product('闭环');inbound(p,wa,'6');inbound(p,wb,'8');source,oid,item=order(p,'10')
    check('cancel open quantity before allocating',admin.cancel(oid,[(item,'2')])['orderStatus']=='NEW')
    preview_input={'orderId':oid,'warehouseIds':[str(wb),str(wa)],'strategy':'PRIORITY_SPLIT','holdSeconds':86400}
    before=(balance(p,wa),balance(p,wb),sql('SELECT COUNT(*) FROM ful_command_record')[0][0])
    preview=admin.api('POST','/fulfillment/order/preview',preview_input)
    check('preview deterministic and versioned',preview==second.api('POST','/fulfillment/order/preview',preview_input) and preview['strategyVersion']==1)
    check('preview makes no commitment or command record',before==(balance(p,wa),balance(p,wb),sql('SELECT COUNT(*) FROM ful_command_record')[0][0]))
    check('preview stable priority plan',[(r['warehouseId'],r['quantity']) for r in preview['plan']]==[(str(wa),'6.000000'),(str(wb),'2.000000')])
    reserve=admin.allocate(oid,[wa,wb]);ra,rb=reserve['reservations'];admin.release(oid,[(ra['id'],'1')])
    check('cancel consumes open before releasing held',admin.cancel(oid,[(item,'2')])['orderStatus']=='RESERVED' and balance(p,wa)[1]==4 and balance(p,wb)[1]==2)
    check('cancel keeps physical and original ordered qty',balance(p,wa)[0]==6 and quantities(oid)[0]==(Decimal(10),Decimal(0),Decimal(6),Decimal(0),Decimal(4)))
    check('zero ship rejected',admin.ship(oid,wa,[(ra['id'],'0')],ok=False)['code']==1080000011)
    check('duplicate reservation rejected',admin.ship(oid,wa,[(ra['id'],'1'),(ra['id'],'1')],ok=False)['code']==1080000011)
    check('cross warehouse reservation rejected',admin.ship(oid,wa,[(rb['id'],'1')],ok=False)['code']==1080000012)
    ship_key='ship-'+RUN
    shipped=admin.ship(oid,wa,[(ra['id'],'2')],ship_key)
    check('partial shipment updates status',shipped['orderStatus']=='PARTIALLY_SHIPPED')
    check('ship deducts physical exactly once',balance(p,wa)==(Decimal(4),Decimal(2)))
    check('same key decimal canonical replay',second.ship(oid,wa,[(ra['id'],'2.000000')],ship_key)==shipped)
    check('same key changed quantity conflicts',admin.ship(oid,wa,[(ra['id'],'1')],ship_key,ok=False)['code']==1080000005)
    check('one approved ERP out and one physical ledger',sql('SELECT status FROM erp_sale_out WHERE id=%s',(shipped['erpSaleOutId'],))[0][0]==20 and sql('SELECT COUNT(*) FROM erp_stock_record WHERE biz_id=%s AND biz_type=50',(shipped['erpSaleOutId'],))[0][0]==1)
    mapping=sql('SELECT si.erp_sale_out_item_id,l.erp_stock_record_id FROM ful_shipment_item si JOIN ful_stock_ledger l ON l.operation_no=%s AND l.reservation_id=si.reservation_id WHERE si.shipment_id=%s',(shipped['shipmentNo'],shipped['shipmentId']))
    check('shipment links ERP item and physical ledger',len(mapping)==1 and all(mapping[0]))
    old=admin.api('GET','/erp/sale-order/get',params={'id':source})
    check('legacy source shows pending excluding cancelled',old['fulfillmentManaged'] and old['fulfillmentId']==oid and old['items'][0]['fulfillmentRemainingQty']=='4.000000' and old['items'][0]['fulfillmentCancelledQty']=='4.000000')
    cancel_key='cancel-'+RUN;closed=admin.cancel(oid,[(item,'4')],cancel_key)
    check('partial close preserves cumulative shipment',closed['orderStatus']=='PARTIALLY_CLOSED' and quantities(oid)[0]==(Decimal(10),Decimal(0),Decimal(0),Decimal(2),Decimal(8)))
    check('cancel replay stable after close',second.cancel(oid,[(item,'4.000000')],cancel_key)==closed)
    check('cancel cannot undo shipped quantities',admin.cancel(oid,[(item,'1')],ok=False)['code']==1080000021)
    check('full closed pending is zero in old page',admin.api('GET','/erp/sale-order/get',params={'id':source})['items'][0]['fulfillmentRemainingQty']=='0.000000')
    page=admin.api('GET','/erp/sale-order/page',params={'no':old['no'],'pageNo':1,'pageSize':20})
    check('legacy list projects cancellation-aware pending quantities',len(page['list'])==1 and page['list'][0]['items'][0]['fulfillmentRemainingQty']=='0.000000')
    for path,method,body,params in [('/erp/sale-out/update-status','PUT',None,{'id':shipped['erpSaleOutId'],'status':10}),('/erp/sale-out/delete','DELETE',None,{'ids':shipped['erpSaleOutId']}),('/erp/sale-order/update-status','PUT',None,{'id':source,'status':10})]:
        check('legacy managed mutation frozen '+path,admin.api(method,path,body,params,ok=False)['code']==1030199000)
    check('client bypass flag cannot create managed out',admin.api('POST','/erp/sale-out/create',{'orderId':source,'accountId':account,'outTime':NOW,'managed':True,'internal':True,'items':[]},ok=False)['code']==1030199000)
    check('cancellation facts retained',len(admin.api('GET','/fulfillment/order/cancellations',params={'orderId':oid}))==3)

    # Roll back after the ERP physical ledger has been written, then retry same key normally.
    fp=product('回滚');inbound(fp,wa,'5');fs,fo,fi=order(fp,'4');fr=admin.allocate(fo,[wa])['reservations'][0]['id'];fk='fault-'+RUN
    before=(balance(fp,wa),quantities(fo),sql('SELECT COUNT(*) FROM erp_sale_out WHERE order_id=%s',(fs,))[0][0])
    failed=fault.ship(fo,wa,[(fr,'2')],fk,ok=False)
    check('isolated after-ERP test fault reached',failed['code']==500 and 'M3_TEST_FAILURE_AFTER_ERP_APPROVAL' in (ROOT/'.local/m3-fault-out.log').read_text(encoding='utf-8',errors='replace'))
    check('failure rolls back H R quantities and ERP document',before==(balance(fp,wa),quantities(fo),sql('SELECT COUNT(*) FROM erp_sale_out WHERE order_id=%s',(fs,))[0][0]))
    check('failure rolls back shipment and command',not sql('SELECT id FROM ful_shipment WHERE order_id=%s',(fo,)) and not sql("SELECT id FROM ful_command_record WHERE command_type='SHIP' AND idempotency_key=%s",(fk,)))
    recovery=admin.ship(fo,wa,[(fr,'2')],fk)
    check('same key succeeds after fault rollback',balance(fp,wa)==(Decimal(3),Decimal(2)) and second.ship(fo,wa,[(fr,'2')],fk)==recovery)

    # Cross-process same-key ship and competing ship/cancel.
    cp=product('并发');inbound(cp,wa,'10');cs,co,ci=order(cp,'6');cr=admin.allocate(co,[wa])['reservations'][0]['id'];ck='concurrent-'+RUN
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        outputs=list(pool.map(lambda n:M3Client(48080 if n%2==0 else 48082).login().ship(co,wa,[(cr,'2')],ck),range(6)))
    check('two JVM same-key shipment is one result',all(v==outputs[0] for v in outputs) and balance(cp,wa)==(Decimal(8),Decimal(4)))
    check('same-key one ERP out',sql('SELECT COUNT(*) FROM erp_sale_out WHERE order_id=%s',(cs,))[0][0]==1)
    for n in range(3):
        rp=product('竞争'+str(n));inbound(rp,wa,'10');rs,ro,ri=order(rp,'6');rr=admin.allocate(ro,[wa])['reservations'][0]['id']
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            a=pool.submit(lambda:M3Client().login().ship(ro,wa,[(rr,'4')],ok=False));b=pool.submit(lambda:M3Client(48082).login().cancel(ro,[(ri,'4')],ok=False));results=[a.result(),b.result()]
        check('ship versus cancel has one legal winner',sum(r['code']==0 for r in results)==1 and balance(rp,wa)[1]==2,results)
        check('racing quantity identity remains intact',quantities(ro)[0][3]+quantities(ro)[0][4]==4)
    fullp=product('全发');inbound(fullp,wa,'1.123456');_,full,fulli=order(fullp,'1.123456');fullr=admin.allocate(full,[wa])['reservations'][0]['id']
    check('full decimal shipment fulfills',admin.ship(full,wa,[(fullr,'1.123456')])['orderStatus']=='FULFILLED' and balance(fullp,wa)==(Decimal(0),Decimal(0)))
    _,allcancel,allci=order(fullp,'2');check('full open cancellation closes without stock',admin.cancel(allcancel,[(allci,'2')])['orderStatus']=='CANCELLED')

    # HMAC over raw bytes; repeat and out-of-order deliveries never affect stock.
    # The independently expiring fixture is asserted below; its scheduled change is unrelated to logistics.
    snapshot=[(x,balance(x,wa),balance(x,wb)) for x in products if x!=ep]
    event='delivery-'+RUN;occurred=datetime.now(timezone.utc).isoformat()
    delivered,raw=callback(shipped['shipmentNo'],event=event,occurred=occurred,tenant=999999)
    check('signed anonymous callback uses integration tenant not header',delivered['code']==0 and delivered['data']['outcome']=='DELIVERED',delivered)
    replay,_=callback(shipped['shipmentNo'],event=event,occurred=occurred,raw=raw,port=48082)
    check('duplicate callback returns original result',replay==delivered)
    late,_=callback(shipped['shipmentNo'],'IN_TRANSIT');check('late transit cannot reverse delivered',late['code']==0 and late['data']['outcome']=='IGNORED_AFTER_DELIVERED')
    conflict,_=callback(shipped['shipmentNo'],'IN_TRANSIT',event=event,occurred=occurred)
    check('same event different payload conflicts',conflict['code']==1080000031)
    check('callback conflict diagnostic committed',sql('SELECT conflict_count,last_conflict_hash FROM ful_callback_event WHERE event_id=%s',(event,))[0][0]==1)
    check('invalid signature rejected',callback(shipped['shipmentNo'],signature='0'*64)[0]['code']==1080000030)
    check('old signature rejected',callback(shipped['shipmentNo'],stamp=str(int(time.time())-301))[0]['code']==1080000030)
    check('wrong integration rejected',callback(shipped['shipmentNo'],integration='unknown-integration')[0]['code']==1080000030)
    check('tampered raw body rejected',callback(shipped['shipmentNo'],raw=raw+b' ',signature=hmac.new(os.environ.get('LOGISTICS_SECRET','local-logistics-demo-secret-change-before-sharing').encode(),str(int(time.time())).encode()+b'\n'+event.encode()+b'\n'+raw,hashlib.sha256).hexdigest(),event=event)[0]['code']==1080000030)
    unknown,_=callback('SHP-'+str(uuid.uuid4()));check('unknown shipment is retryable business failure',unknown['code']==1080000032)
    simulated=admin.api('POST','/fulfillment/logistics/simulate',{'shipmentId':recovery['shipmentId'],'eventType':'DELIVERED'})
    check('simulator sends actual signed HTTP callback',simulated['outcome']=='DELIVERED')
    check('all logistics leaves physical and reserved unchanged',snapshot==[(x,balance(x,wa),balance(x,wb)) for x in products if x!=ep])
    check('shipment page includes mapped items and delivery events',admin.api('GET','/fulfillment/shipment/page',params={'orderId':oid,'pageNo':1,'pageSize':20})['list'][0]['status']=='DELIVERED')

    while time.time()<=expiry_deadline+0.1:time.sleep(min(5,max(0.1,expiry_deadline+0.2-time.time())))
    if os.getenv('M3_EXPECT_AUTO_EXPIRY','1')=='1':
        limit=time.monotonic()+30
        while balance(ep,wa)[1]!=0 and time.monotonic()<limit:time.sleep(.2)
        check('automatically expired held cannot ship',admin.ship(expiry,wa,[(expired['id'],'1')],ok=False)['code']==1080000012)
        check('auto expiry preserves physical and releases reserved',balance(ep,wa)==(Decimal(2),Decimal(0)))
        check('auto expiry reopens quantity with one expiry fact',quantities(expiry)[0][1]==2 and sql("SELECT COUNT(*) FROM ful_stock_ledger WHERE reservation_id=%s AND event_type='EXPIRE'",(expired['id'],))[0][0]==1)
    else:
        # Only for reproducing the archived M3 binary before automatic expiry existed.
        check('expired held cannot ship',admin.ship(expiry,wa,[(expired['id'],'1')],ok=False)['code']==1080000020)
        check('expiry rejection changes no stock',balance(ep,wa)==(Decimal(2),Decimal(2)))
        admin.release(expiry,[(expired['id'],'2')]);check('expired reservation can be manually released',balance(ep,wa)==(Decimal(2),Decimal(0)))
    invariant(products)
    check('all shipment quantities match physical ERP details',not sql('SELECT si.id FROM ful_shipment_item si JOIN erp_sale_out_items ei ON ei.id=si.erp_sale_out_item_id WHERE si.quantity<>ei.`count`'))
    check('consumed reservations match shipment totals',not sql('SELECT r.id FROM ful_reservation r WHERE r.consumed_qty<>(SELECT COALESCE(SUM(si.quantity),0) FROM ful_shipment_item si WHERE si.tenant_id=r.tenant_id AND si.reservation_id=r.id)'))
    E['ids']={'order':oid,'source':source,'item':item,'shipment':shipped,'recovery':recovery,'warehouse_a':wa,'warehouse_b':wb,'products':products}
    E['result']='passed'
if __name__=='__main__':
    try:main()
    except Exception as exc:E['result']='failed';E['error']=str(exc);raise
    finally:
        (ROOT/'../学习资料/10-验收证据'/os.getenv('M3_EVIDENCE','M3-acceptance.json')).write_text(json.dumps(E,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
        print('M3 acceptance',E.get('result'),len(E['checks']),'checks')
