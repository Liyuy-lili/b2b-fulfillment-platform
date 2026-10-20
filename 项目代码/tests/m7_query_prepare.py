"""Finish explicitly synthetic query fixtures before any timed measurement."""
from datetime import datetime,timezone
import m7_support as h
seed=h.load('M7.3-query-seed.json');DB=seed['database'];T=seed['second_tenant'];rt=h.Runtime(DB,10)
E={'database':DB,'artifact_sha256':h.sha(h.JAR),'run_at':datetime.now(timezone.utc).isoformat(),'checks':[],'origin':'SQL synthetic orders; actual tenant-specific masters and two warehouse inbounds per tenant via HTTP. Fixture preparation is outside timed windows.'}
def check(name,value,detail=None):
    E['checks'].append(dict(name=name,passed=bool(value),detail=detail));print(name,value,flush=True)
    assert value,name
q=lambda s,a=():h.sql(DB,s,a)
try:
    E['migration']=h.shell('scripts/Migrate-Database.ps1','-Action','migrate','-Database',DB,label='m7-query-v8')
    rt.start(48085,'query-prepare');E['tenants']={}
    for t in [1,T]:
        c=h.Client(48085,t).login('admin' if t==1 else 'm7querytenant')
        def create(kind,body):return c.api('POST','/erp/'+kind+'/create',body)
        uid=q('SELECT id FROM system_users WHERE tenant_id=%s AND username=%s',(t,'admin' if t==1 else 'm7querytenant'))[0][0]
        if t==1:
            p=seed['template']['product'];customer=seed['template']['customer'];unit=q('SELECT unit_id FROM erp_product WHERE id=%s',(p,))[0][0];account=q('SELECT account_id FROM ful_order WHERE id=%s',(seed['template']['order'],))[0][0]
        else:
            unit=create('product-unit',{'name':'M7租户件','status':0});cat=create('product-category',{'name':'M7租户分类','code':'M7T'+str(t),'parentId':0,'sort':1,'status':0})
            customer=create('customer',{'name':'M7租户客户','sort':1,'status':0});account=create('account',{'name':'M7租户账户','no':'M7T'+str(t),'sort':1,'status':0})
            p=create('product',{'name':'M7租户商品','barCode':'M7T'+str(t),'unitId':unit,'categoryId':cat,'status':0,'salePrice':'2.345678'})
            # Correct staged clones, never main or another tenant. No business
            # acceptance claim is made for SQL-generated orders.
            for table,cols,args in [('ful_order','customer_id=%s,account_id=%s,owner_user_id=%s',(customer,account,uid)),('erp_sale_order','customer_id=%s,account_id=%s',(customer,account)),('ful_order_item','product_id=%s,unit_id=%s',(p,unit)),('erp_sale_order_items','product_id=%s,product_unit_id=%s',(p,unit))]:
                q('UPDATE '+table+' SET '+cols+',creator=%s,updater=%s WHERE tenant_id=%s AND id>=10000000',(*args,str(uid),str(uid),t))
        supplier=create('supplier',{'name':'M7性能供应商'+str(t),'sort':1,'status':0});warehouses=[]
        for n in [1,2]:
            w=create('warehouse',{'name':'M7性能仓'+str(t)+'-'+str(n),'sort':n,'status':0,'warehousePrice':'0','truckagePrice':'0'});warehouses.append(w)
            inbound=create('stock-in',{'supplierId':supplier,'inTime':datetime.now().isoformat(timespec='seconds'),'items':[{'productId':p,'warehouseId':w,'count':'100.000001','productPrice':'0'}]});c.api('PUT','/erp/stock-in/update-status',params={'id':inbound,'status':20})
        E['tenants'][str(t)]={'user':uid,'customer':customer,'account':account,'product':p,'unit':unit,'warehouses':warehouses}
    for table,ref,col in [('ful_order','erp_customer','customer_id'),('ful_order','erp_account','account_id'),('ful_order','system_users','owner_user_id'),('ful_order_item','erp_product','product_id'),('ful_order_item','erp_product_unit','unit_id'),('erp_sale_order','erp_customer','customer_id'),('erp_sale_order_items','erp_product','product_id')]:
        check('valid same-tenant references '+table+'.'+col,q('SELECT COUNT(*) FROM '+table+' o LEFT JOIN '+ref+' r ON r.id=o.'+col+' AND r.tenant_id=o.tenant_id WHERE r.id IS NULL')[0][0]==0)
    check('all order items belong to same tenant order',q('SELECT COUNT(*) FROM ful_order_item i LEFT JOIN ful_order o ON o.id=i.order_id AND o.tenant_id=i.tenant_id WHERE o.id IS NULL')[0][0]==0)
    check('quantity identity on every synthetic order item',q('SELECT COUNT(*) FROM ful_order_item WHERE ordered_qty<>open_qty+reserved_qty+shipped_qty+cancelled_qty OR returned_qty>shipped_qty')[0][0]==0)
    E['counts']=q('SELECT tenant_id,status,COUNT(*) FROM ful_order GROUP BY tenant_id,status');check('four actual warehouse stock rows',q('SELECT COUNT(*) FROM erp_stock')[0][0]==4)
    check('current migrations V0-V8',tuple(r[0] for r in q('SELECT version FROM ful_flyway_schema_history ORDER BY installed_rank'))==tuple(map(str,range(9))))
    E['result']='passed'
except Exception as error:E.update(result='failed',error=str(error));raise
finally:E['owned_stopped']=rt.close();h.save('M7.3-query-prepare.json',E)
