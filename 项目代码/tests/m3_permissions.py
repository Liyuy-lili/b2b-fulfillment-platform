"""M3 function/owner/tenant boundaries and trusted logistics integration routing."""
import json,uuid
from datetime import datetime,timezone
from m3_acceptance import M3Client,callback
from m1_acceptance import ROOT,sql
from m2_acceptance import balance
E={'run_at':datetime.now(timezone.utc).isoformat(),'checks':[],'ids':{}};RUN='M3P'+uuid.uuid4().hex[:7];NOW=datetime.now().isoformat(timespec='seconds')
def check(name,ok,detail=None):
    E['checks'].append({'name':name,'passed':bool(ok),'detail':detail})
    if not ok:raise AssertionError(name+': '+str(detail))
def main():
    admin=M3Client().login();f=json.loads((ROOT/'../学习资料/10-验收证据/M2-acceptance.json').read_text(encoding='utf-8'))['ids']
    menus=[r[0] for r in sql("SELECT id FROM system_menu WHERE deleted=0 AND (permission LIKE 'erp:%%' OR id BETWEEN 50000 AND 50008 OR id=597)")]
    role=admin.api('POST','/system/role/create',{'name':RUN,'code':RUN,'status':0,'sort':1})
    def assign(ids):admin.api('POST','/system/permission/assign-role-menu',{'roleId':role,'menuIds':ids})
    assign(menus)
    def user(suffix,grant=True):
        name=RUN+suffix;uid=admin.api('POST','/system/user/create',{'username':name,'nickname':name,'password':'admin123'})
        if grant:admin.api('POST','/system/permission/assign-user-role',{'userId':uid,'roleIds':[role]})
        return uid,M3Client().login(name)
    alice_id,alice=user('Alice');_,bob=user('Bob');_,none=user('None',False)
    product=admin.create('product',{'name':RUN,'barCode':RUN,'categoryId':f['category'],'unitId':f['unit'],'status':0,'salePrice':'0'})
    incoming=admin.create('stock-in',{'supplierId':f['supplier'],'inTime':NOW,'items':[{'productId':product,'warehouseId':f['warehouse_a'],'count':'10','productPrice':'0'}]});admin.approve('stock-in',incoming)
    source=alice.create('sale-order',{'customerId':f['customer'],'accountId':f['account'],'orderTime':NOW,'discountPercent':'0','items':[{'productId':product,'productPrice':'0','count':'5','taxPercent':'0'}]});alice.approve('sale-order',source);order=alice.bind(source)['orderId']
    item=alice.api('GET','/fulfillment/order/get',params={'id':order})['items'][0]['id']
    preview={'orderId':order,'warehouseIds':[str(f['warehouse_a'])],'strategy':'PRIORITY_SPLIT','holdSeconds':86400}
    check('preview requires function permission',none.api('POST','/fulfillment/order/preview',preview,ok=False)['code']==403)
    check('preview checks source owner',bob.api('POST','/fulfillment/order/preview',preview,ok=False)['code']==1080000003)
    reservation=alice.allocate(order,[f['warehouse_a']])['reservations'][0]['id']
    check('ship function permission independent',none.ship(order,f['warehouse_a'],[(reservation,'1')],ok=False)['code']==403)
    check('cancel function permission independent',none.cancel(order,[(item,'1')],ok=False)['code']==403)
    check('ship requires order owner',bob.ship(order,f['warehouse_a'],[(reservation,'1')],ok=False)['code']==1080000003)
    check('cancel requires order owner',bob.cancel(order,[(item,'1')],ok=False)['code']==1080000003)
    key='ship-auth-'+RUN;shipped=alice.ship(order,f['warehouse_a'],[(reservation,'1')],key)
    check('owner can ship',shipped['orderStatus']=='PARTIALLY_SHIPPED' and balance(product,f['warehouse_a'])==(9,4))
    check('other owner cannot read known shipment',bob.api('GET','/fulfillment/shipment/get',params={'id':shipped['shipmentId']},ok=False)['code']==1080000003)
    check('other owner cannot list shipments',bob.api('GET','/fulfillment/shipment/page',params={'orderId':order},ok=False)['code']==1080000003)
    check('other owner cannot simulate known shipment',bob.api('POST','/fulfillment/logistics/simulate',{'shipmentId':shipped['shipmentId'],'eventType':'DELIVERED'},ok=False)['code']==1080000003)
    check('other owner cannot inspect cancellation history',bob.api('GET','/fulfillment/order/cancellations',params={'orderId':order},ok=False)['code']==1080000003)
    check('shipment page size bounded',admin.api('GET','/fulfillment/shipment/page',params={'orderId':order,'pageSize':101},ok=False)['code']==400)
    assign([i for i in menus if i not in (50005,50006,50007,50008)])
    check('ship replay rechecks current function permission',alice.ship(order,f['warehouse_a'],[(reservation,'1')],key,ok=False)['code']==403)
    check('shipment query requires its permission',alice.api('GET','/fulfillment/shipment/get',params={'id':shipped['shipmentId']},ok=False)['code']==403)
    check('simulation requires its permission',alice.api('POST','/fulfillment/logistics/simulate',{'shipmentId':shipped['shipmentId'],'eventType':'DELIVERED'},ok=False)['code']==403)
    assign(menus);check('replay restored permission returns original result',alice.ship(order,f['warehouse_a'],[(reservation,'1')],key)==shipped)
    ck='cancel-auth-'+RUN;cancelled=alice.cancel(order,[(item,'1')],ck)
    assign([i for i in menus if i!=50005]);check('cancel replay rechecks permission',alice.cancel(order,[(item,'1')],ck,ok=False)['code']==403);assign(menus)
    package=admin.api('POST','/system/tenant-package/create',{'name':RUN+'套餐','status':0,'menuIds':menus})
    tenant=admin.api('POST','/system/tenant/create',{'name':RUN+'隔离租户','contactName':'M3测试','status':0,'packageId':package,'expireTime':'2035-12-31T23:59:59','accountCount':10,'username':RUN+'Tenant','password':'admin123','websites':[]})
    other=M3Client(tenant=tenant).login(RUN+'Tenant')
    check('other tenant cannot ship known order',other.ship(order,f['warehouse_a'],[(reservation,'1')],ok=False)['code']==1080000003)
    check('other tenant cannot cancel known item',other.cancel(order,[(item,'1')],ok=False)['code']==1080000003)
    check('other tenant cannot query known shipment',other.api('GET','/fulfillment/shipment/get',params={'id':shipped['shipmentId']},ok=False)['code']==1080000022)
    # Foreign tenant has its own shipment; integration local-demo remains bound to tenant 1.
    unit=other.create('product-unit',{'name':RUN+'件','status':0});category=other.create('product-category',{'name':RUN,'code':RUN,'parentId':0,'sort':1,'status':0})
    fp=other.create('product',{'name':RUN,'barCode':RUN,'categoryId':category,'unitId':unit,'status':0,'salePrice':'0'})
    wh=other.create('warehouse',{'name':RUN+'隔离仓','sort':1,'status':0,'warehousePrice':'0','truckagePrice':'0'})
    supplier=other.create('supplier',{'name':RUN,'sort':1,'status':0});customer=other.create('customer',{'name':RUN,'sort':1,'status':0});account=other.create('account',{'name':RUN,'no':RUN,'sort':1,'status':0})
    inc=other.create('stock-in',{'supplierId':supplier,'inTime':NOW,'items':[{'productId':fp,'warehouseId':wh,'count':'2','productPrice':'0'}]});other.approve('stock-in',inc)
    src=other.create('sale-order',{'customerId':customer,'accountId':account,'orderTime':NOW,'discountPercent':'0','items':[{'productId':fp,'productPrice':'0','count':'2','taxPercent':'0'}]});other.approve('sale-order',src);fo=other.bind(src)['orderId'];fr=other.allocate(fo,[wh])['reservations'][0]['id'];foreign=other.ship(fo,wh,[(fr,'1')])
    response,_=callback(foreign['shipmentNo'],tenant=tenant)
    check('signed integration cannot route into body or header tenant',response['code']==1080000032,response)
    check('foreign shipment remains SHIPPED',other.api('GET','/fulfillment/shipment/get',params={'id':foreign['shipmentId']})['status']=='SHIPPED')
    bad=alice.api('POST','/fulfillment/shipment/confirm',{'orderId':order,'warehouseId':str(f['warehouse_a']),'items':[{'id':reservation,'quantity':'1'}],'carrierCode':'SIMULATED','trackingNo':'SPOOF','tenantId':tenant,'ownerUserId':'999'},headers={'Idempotency-Key':uuid.uuid4().hex})
    check('body tenant spoof stays in authenticated tenant',sql('SELECT tenant_id FROM ful_shipment WHERE id=%s',(bad['shipmentId'],))[0][0]==1)
    check('failed unauthorized operations preserve expected quantities',sql('SELECT reserved_qty,shipped_qty,cancelled_qty FROM ful_order_item WHERE id=%s',(item,))[0]==(2,2,1))
    E['ids']={'owner':alice_id,'tenant':tenant,'product':product,'order':order,'foreign_shipment':foreign};E['result']='passed'
if __name__=='__main__':
    try:main()
    except Exception as exc:E['result']='failed';E['error']=str(exc);raise
    finally:
        (ROOT/'../学习资料/10-验收证据/M3-permissions.json').write_text(json.dumps(E,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
        print('M3 permissions',E.get('result'),len(E['checks']),'checks')
