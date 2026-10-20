"""SQL-only synthetic performance data; real API template, isolated schema.
Labels synthetic rows explicitly; never presented as business acceptance writes.
"""
import json,os,subprocess,time
from datetime import datetime,timezone
import pymysql
import m7_support as m
DB='fulfillment_m7_query_'+datetime.now().strftime('%Y%m%d_%H%M%S');E={'run_at':datetime.now(timezone.utc).isoformat(),'database':DB,'checks':[],'data_origin':'Real HTTP template; explicitly labelled SQL-cloned synthetic benchmark orders/items, not business acceptance.'}
def check(name,ok,detail=None):
    E['checks'].append({'name':name,'passed':bool(ok),'detail':detail});print(('PASS ' if ok else 'FAIL ')+name,flush=True)
    if not ok:raise AssertionError(name)
def clone_table(con,table,template,rows):
    with con.cursor() as cur:
        cur.execute('SELECT * FROM '+table+' WHERE id=%s',(template,));keys=[x[0] for x in cur.description];base=dict(zip(keys,cur.fetchone()));batch=[]
        for changes in rows:
            values=dict(base);values.update(changes);batch.append(tuple(values[k] for k in keys))
            if len(batch)==500:cur.executemany('INSERT INTO '+table+' (`'+'`,`'.join(keys)+'`) VALUES ('+','.join(['%s']*len(keys))+')',batch);con.commit();batch=[]
        if batch:cur.executemany('INSERT INTO '+table+' (`'+'`,`'.join(keys)+'`) VALUES ('+','.join(['%s']*len(keys))+')',batch);con.commit()
runtime=m.Runtime(DB,10)
try:
    E['commands']=m.initialize(DB);runtime.start(48085,'query-template');c=m.Client(48085).login()
    def create(kind,body):return c.api('POST','/erp/'+kind+'/create',body)
    unit=create('product-unit',{'name':'M7性能件','status':0});category=create('product-category',{'name':'M7性能分类','code':'M7QUERY','parentId':0,'sort':1,'status':0});customer=create('customer',{'name':'M7合成客户','sort':1,'status':0});account=create('account',{'name':'M7合成账户','no':'M7QUERY','sort':1,'status':0});product=create('product',{'name':'M7查询模板商品','barCode':'M7QUERY','categoryId':category,'unitId':unit,'status':0,'salePrice':'2.345678'})
    source=create('sale-order',{'customerId':customer,'accountId':account,'orderTime':datetime.now().isoformat(timespec='seconds'),'items':[{'productId':product,'count':'1.000001','productPrice':'2.345678','taxPercent':'0'}]});c.api('PUT','/erp/sale-order/update-status',params={'id':source,'status':20});order=c.api('POST','/fulfillment/order/bind',{'erpOrderId':str(source)},key='m7-template')['orderId']
    q=lambda s,a=():m.sql(DB,s,a)
    source_item=q('SELECT id FROM erp_sale_order_items WHERE order_id=%s',(source,))[0][0];item=q('SELECT id FROM ful_order_item WHERE order_id=%s',(order,))[0][0]
    # Two actual tenant accounts; synthetic tenant-2 masters are copied from the
    # per-tenant template only after creating that tenant through its admin API.
    menus=[x[0] for x in q('SELECT id FROM system_menu WHERE deleted=0')];package=c.api('POST','/system/tenant-package/create',{'name':'M7Query','status':0,'menuIds':menus});tenant=c.api('POST','/system/tenant/create',{'name':'M7QueryTenant','contactName':'M7','status':0,'packageId':package,'expireTime':'2035-12-31T23:59:59','accountCount':20,'username':'m7querytenant','password':'admin123','websites':[]})
    check('second actual tenant distinct',tenant!=1);E['second_tenant']=tenant
    with pymysql.connect(host='127.0.0.1',port=33306,user='fulfillment',password='fulfillment-dev',database=DB,charset='utf8mb4') as con:
        for size in [10000,50000]:
            lower=0 if size==10000 else 10000
            rows=[(t,n) for t in [1,tenant] for n in range(lower,size)]
            ident=lambda t,n:10000000+t*100000+n
            clone_table(con,'erp_sale_order',source,({'id':ident(t,n),'tenant_id':t,'no':f'M7SYN-T{t}-{n:06d}'} for t,n in rows))
            clone_table(con,'erp_sale_order_items',source_item,({'id':ident(t,n),'order_id':ident(t,n),'tenant_id':t} for t,n in rows))
            clone_table(con,'ful_order',int(order),({'id':ident(t,n),'erp_order_id':ident(t,n),'tenant_id':t,'order_no':f'M7SYN-T{t}-{n:06d}','status':'WAIT_STOCK' if n%10==0 else 'NEW','allocation_attempted':b'\1' if n%10==0 else b'\0'} for t,n in rows))
            clone_table(con,'ful_order_item',item,({'id':ident(t,n),'erp_order_item_id':ident(t,n),'order_id':ident(t,n),'tenant_id':t} for t,n in rows))
            plans=q('EXPLAIN FORMAT=JSON SELECT * FROM ful_order WHERE tenant_id=1 AND deleted=0 AND status=%s ORDER BY id DESC LIMIT 50',('WAIT_STOCK',));E['scale_'+str(size)]={'orders_per_tenant':size,'counts':q('SELECT tenant_id,status,COUNT(*) FROM ful_order GROUP BY tenant_id,status'),'baseline_explain':json.loads(plans[0][0])};check('synthetic scale '+str(size),q('SELECT COUNT(*) FROM ful_order WHERE tenant_id=%s',(tenant,))[0][0]==size)
    E.update(template={'order':order,'source':source,'source_item':source_item,'item':item,'product':product,'customer':customer},artifact_sha256=m.sha(m.JAR),result='passed')
except Exception as error:E.update(result='failed',error=str(error));raise
finally:
    E['owned_stopped']=runtime.close();m.save('M7.3-query-seed.json',E);print('query seed',E.get('result'),flush=True)
