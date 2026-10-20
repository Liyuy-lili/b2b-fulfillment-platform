"""Create a named local scenario for real browser actions; does not allocate or ship."""
import json,uuid
from datetime import datetime,timezone
from m3_acceptance import M3Client
from m1_acceptance import ROOT
c=M3Client().login();f=json.loads((ROOT/'../学习资料/10-验收证据/M2-acceptance.json').read_text(encoding='utf-8'))['ids'];run=uuid.uuid4().hex[:6];now=datetime.now().isoformat(timespec='seconds')
p=c.create('product',{'name':'M3演示办公耗材-'+run,'barCode':'M3UI'+run,'categoryId':f['category'],'unitId':f['unit'],'status':0,'salePrice':'9.9'})
warehouses=[]
for label,q,sort in [('华东仓','6',1),('华南仓','8',2)]:
    name='M3演示'+label+'-'+run;w=c.create('warehouse',{'name':name,'sort':sort,'status':0,'warehousePrice':'0','truckagePrice':'0'});warehouses.append({'id':str(w),'name':name,'initial':q})
    stockin=c.create('stock-in',{'supplierId':f['supplier'],'inTime':now,'items':[{'productId':p,'warehouseId':w,'count':q,'productPrice':'0'}]});c.approve('stock-in',stockin)
source=c.create('sale-order',{'customerId':f['customer'],'accountId':f['account'],'orderTime':now,'discountPercent':'0','items':[{'productId':p,'count':'10','productPrice':'9.9','taxPercent':'13'}]});c.approve('sale-order',source);order=c.bind(source)['orderId'];view=c.api('GET','/fulfillment/order/get',params={'id':order})
e={'run_at':datetime.now(timezone.utc).isoformat(),'run':run,'source':source,'order':order,'orderNo':view['orderNo'],'product':p,'item':view['items'][0]['id'],'warehouses':warehouses,'initial_order':view}
(ROOT/'../学习资料/10-验收证据/M3-ui-fixture.json').write_text(json.dumps(e,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(e,ensure_ascii=True))
