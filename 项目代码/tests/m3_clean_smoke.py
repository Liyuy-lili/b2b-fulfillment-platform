"""Positive M3 end-to-end workflow in independently installed DB; no main-DB fallbacks."""
import json,os,uuid
from datetime import datetime,timezone
from m1_acceptance import Client,ROOT,sql
E={'run_at':datetime.now(timezone.utc).isoformat(),'database':os.environ['DB_NAME'],'checks':[]}
def check(name,ok,detail=None):
    E['checks'].append({'name':name,'passed':bool(ok),'detail':detail})
    if not ok:raise AssertionError(name+': '+str(detail))
try:
    f=json.loads((ROOT/'../学习资料/10-验收证据'/os.environ['M1_EVIDENCE']).read_text(encoding='utf-8'))['ids'];admin=Client().login();now=datetime.now().isoformat(timespec='seconds');run='M3C'+uuid.uuid4().hex[:6]
    supplier=admin.create('supplier',{'name':run,'status':0,'sort':1})
    incoming=admin.create('stock-in',{'supplierId':supplier,'inTime':now,'items':[{'productId':f['product'],'warehouseId':f['warehouse'],'count':'5','productPrice':'0'}]});admin.approve('stock-in',incoming)
    source=admin.create('sale-order',{'customerId':f['customer'],'accountId':f['account'],'orderTime':now,'discountPercent':'0','items':[{'productId':f['product'],'count':'3','productPrice':'0','taxPercent':'0'}]});admin.approve('sale-order',source)
    order=admin.bind(source)['orderId'];item=admin.api('GET','/fulfillment/order/get',params={'id':order})['items'][0]['id']
    body={'orderId':order,'warehouseIds':[str(f['warehouse'])],'strategy':'PRIORITY_SPLIT','holdSeconds':86400}
    check('fresh install preview succeeds',admin.api('POST','/fulfillment/order/preview',body)['sufficient'])
    reserve=admin.api('POST','/fulfillment/order/allocate',body,headers={'Idempotency-Key':uuid.uuid4().hex});rid=reserve['reservations'][0]['id']
    check('fresh install allocates',reserve['outcome']=='ALLOCATED')
    ship_body={'orderId':order,'warehouseId':str(f['warehouse']),'items':[{'id':rid,'quantity':'1.000001'}],'carrierCode':'SIMULATED','trackingNo':run};key=uuid.uuid4().hex
    shipment=admin.api('POST','/fulfillment/shipment/confirm',ship_body,headers={'Idempotency-Key':key})
    check('fresh install partial shipment succeeds',shipment['orderStatus']=='PARTIALLY_SHIPPED')
    check('fresh install shipment replay exact',admin.api('POST','/fulfillment/shipment/confirm',ship_body,headers={'Idempotency-Key':key})==shipment)
    cancel=admin.api('POST','/fulfillment/order/cancel',{'orderId':order,'items':[{'id':item,'quantity':'1.999999'}],'reason':'fresh install close'},headers={'Idempotency-Key':uuid.uuid4().hex})
    check('fresh install partial close succeeds',cancel['orderStatus']=='PARTIALLY_CLOSED')
    stock=admin.api('GET','/fulfillment/stock/get',params={'productId':f['product'],'warehouseId':f['warehouse']})
    check('fresh install H R A exact after ship and cancel',stock['physical']=='3.999999' and stock['reserved']=='0.000000' and stock['available']=='3.999999')
    check('fresh install signed simulator succeeds',admin.api('POST','/fulfillment/logistics/simulate',{'shipmentId':shipment['shipmentId'],'eventType':'DELIVERED'})['outcome']=='DELIVERED')
    page=admin.api('GET','/fulfillment/shipment/page',params={'orderId':order})
    check('fresh install shipment and callback persist',page['list'][0]['status']=='DELIVERED' and len(page['list'][0]['events'])==1)
    check('fresh install all versions recorded',sql('SELECT version FROM ful_flyway_schema_history ORDER BY installed_rank')==(('0',),('1',),('2',),('3',)))
    E['ids']={'order':order,'shipment':shipment};E['result']='passed'
except Exception as exc:E['result']='failed';E['error']=str(exc);raise
finally:
    (ROOT/'../学习资料/10-验收证据/M3-clean-smoke.json').write_text(json.dumps(E,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('M3 clean smoke',E.get('result'),len(E['checks']),'checks')
