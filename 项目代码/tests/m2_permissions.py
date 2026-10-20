"""New allocation/release auth is verified independently of inventory success cases."""
import json,uuid,os
from datetime import datetime,timezone
from m2_acceptance import M2Client
from m1_acceptance import ROOT,sql

E={'date':'2026-10-18','checks':[],'ids':{}};RUN='M2P'+uuid.uuid4().hex[:7];NOW=datetime.now().isoformat(timespec='seconds')
def check(name,ok,detail=None):
    E['checks'].append({'name':name,'passed':bool(ok),'detail':detail})
    if not ok:raise AssertionError(name+': '+str(detail))
def main():
    admin=M2Client().login();f=json.loads((ROOT/'../学习资料/10-验收证据'/os.getenv('M2_BASE_EVIDENCE','M2-acceptance.json')).read_text(encoding='utf-8'))['ids']
    menu_ids=[r[0] for r in sql("SELECT id FROM system_menu WHERE deleted=0 AND (permission LIKE 'erp:%%' OR id BETWEEN 50000 AND 50004 OR id=597)")]
    role=admin.api('POST','/system/role/create',{'name':RUN,'code':RUN,'status':0,'sort':1})
    admin.api('POST','/system/permission/assign-role-menu',{'roleId':role,'menuIds':menu_ids})
    def user(suffix,grant=True):
        name=RUN+suffix;uid=admin.api('POST','/system/user/create',{'username':name,'nickname':name,'password':'admin123'})
        if grant:admin.api('POST','/system/permission/assign-user-role',{'userId':uid,'roleIds':[role]})
        return uid,M2Client().login(name)
    alice_id,alice=user('Alice');_,bob=user('Bob');_,no_role=user('None',False)
    p=admin.create('product',{'name':RUN,'barCode':RUN,'categoryId':f['category'],'unitId':f['unit'],'status':0,'salePrice':'0'})
    incoming=admin.create('stock-in',{'supplierId':f['supplier'],'inTime':NOW,'items':[{'productId':p,'warehouseId':f['warehouse_a'],'count':'5','productPrice':'0'}]});admin.approve('stock-in',incoming)
    source=alice.create('sale-order',{'customerId':f['customer'],'orderTime':NOW,'discountPercent':'0','items':[{'productId':p,'productPrice':'0','count':'3','taxPercent':'0'}]});alice.approve('sale-order',source);order=alice.bind(source)['orderId']
    check('no allocate function permission',no_role.allocate(order,[f['warehouse_a']],ok=False)['code']==403)
    check('other owner cannot allocate',bob.allocate(order,[f['warehouse_a']],ok=False)['code']==1080000003)
    key='auth'+RUN;result=alice.allocate(order,[f['warehouse_a']],key=key)
    check('owner can allocate authorized tenant warehouse',result['outcome']=='ALLOCATED')
    check('same key is scoped to actor',admin.allocate(order,[f['warehouse_a']],key=key)['outcome']=='NOTHING_TO_ALLOCATE')
    reservation=result['reservations'][0]['id']
    check('other owner cannot list reservations',bob.api('GET','/fulfillment/order/reservations',params={'orderId':order},ok=False)['code']==1080000003)
    check('other owner cannot release',bob.release(order,[(reservation,'1')],ok=False)['code']==1080000003)
    check('foreign order reservation rejected',admin.release(f['split_order'],[(reservation,'1')],ok=False)['code']==1080000012)
    admin.api('POST','/system/permission/assign-role-menu',{'roleId':role,'menuIds':[i for i in menu_ids if i not in (50002,50003)]})
    check('replay checks current allocate permission',alice.allocate(order,[f['warehouse_a']],key=key,ok=False)['code']==403)
    check('release permission independently enforced',alice.release(order,[(reservation,'1')],ok=False)['code']==403)
    admin.api('POST','/system/permission/assign-role-menu',{'roleId':role,'menuIds':menu_ids})
    check('owner can release after permission restored using same key in different command type',alice.release(order,[(reservation,'1')],key=key)['status']=='WAIT_STOCK')
    package=admin.api('POST','/system/tenant-package/create',{'name':RUN+'套餐','status':0,'menuIds':menu_ids})
    tenant=admin.api('POST','/system/tenant/create',{'name':RUN+'隔离租户','contactName':'M2测试','status':0,'packageId':package,'expireTime':'2035-12-31T23:59:59','accountCount':10,'username':RUN+'Tenant','password':'admin123','websites':[]})
    other=M2Client(tenant=tenant).login(RUN+'Tenant')
    check('other tenant cannot allocate known order',other.allocate(order,[f['warehouse_a']],ok=False)['code']==1080000003)
    check('other tenant cannot release known reservation',other.release(order,[(reservation,'1')],ok=False)['code']==1080000003)
    check('other tenant cannot inspect H R A',other.api('GET','/fulfillment/stock/get',params={'productId':p,'warehouseId':f['warehouse_a']},ok=False)['code']==1080000010)
    # A malformed/unknown body cannot supply the server-side tenant or owner.
    spoof={'orderId':order,'strategy':'PRIORITY_SPLIT','warehouseIds':[str(f['warehouse_a'])],'holdSeconds':900,'tenantId':tenant,'ownerUserId':'999'}
    check('body tenant spoof does not change ownership',alice.api('POST','/fulfillment/order/allocate',spoof,headers={'Idempotency-Key':uuid.uuid4().hex})['outcome']=='ALLOCATED')
    check('stock row remains tenant one',sql('SELECT tenant_id FROM erp_stock WHERE product_id=%s',(p,))[0][0]==1)
    # Primary base unit cannot be edited beneath existing reservations.
    other_unit=admin.create('product-unit',{'name':RUN+'另一单位','status':0})
    update={'id':p,'name':RUN,'barCode':RUN,'categoryId':f['category'],'unitId':other_unit,'status':0,'salePrice':'0'}
    check('base unit immutable beneath stock commitments',admin.api('PUT','/erp/product/update',update,ok=False)['code']==1030198001)
    check('source and stock unit identity unchanged',sql('SELECT unit_id FROM erp_product WHERE id=%s',(p,))[0][0]==f['unit'])
    E['ids']={'owner':alice_id,'tenant':tenant,'product':p,'order':order};E['result']='passed'
if __name__=='__main__':
    try:main()
    except Exception as exc:E['result']='failed';E['error']=str(exc);raise
    finally:
        (ROOT/'../学习资料/10-验收证据'/os.getenv('M2_PERMISSIONS_EVIDENCE','M2-permissions.json')).write_text(json.dumps(E,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
        print('M2 permissions',E.get('result'),len(E['checks']),'checks')
