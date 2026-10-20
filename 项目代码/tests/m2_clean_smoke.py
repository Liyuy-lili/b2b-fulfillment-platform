"""Positive M2 workflow in the independently rebuilt database (API_BASE/DB_NAME set by runner)."""
import json,os,uuid
from datetime import datetime
from m1_acceptance import Client,ROOT,sql
E={'date':'2026-10-18','database':os.environ['DB_NAME'],'checks':[]}
def check(name,ok):
    E['checks'].append({'name':name,'passed':bool(ok)})
    if not ok:raise AssertionError(name)
try:
    f=json.loads((ROOT/'../学习资料/10-验收证据'/os.environ['M1_EVIDENCE']).read_text(encoding='utf-8'))['ids'];admin=Client().login();now=datetime.now().isoformat(timespec='seconds')
    supplier=admin.create('supplier',{'name':'M2clean'+uuid.uuid4().hex[:6],'status':0,'sort':1})
    incoming=admin.create('stock-in',{'supplierId':supplier,'inTime':now,'items':[{'productId':f['product'],'warehouseId':f['warehouse'],'count':'2.000001','productPrice':'0'}]});admin.approve('stock-in',incoming)
    source=admin.create('sale-order',{'customerId':f['customer'],'orderTime':now,'discountPercent':'0','items':[{'productId':f['product'],'count':'2','productPrice':'0','taxPercent':'0'}]});admin.approve('sale-order',source)
    order=admin.bind(source)['orderId'];key=uuid.uuid4().hex
    body={'orderId':order,'strategy':'PRIORITY_SPLIT','warehouseIds':[str(f['warehouse'])],'holdSeconds':900}
    allocated=admin.api('POST','/fulfillment/order/allocate',body,headers={'Idempotency-Key':key})
    check('fresh install reserve succeeds',allocated['status']=='RESERVED' and allocated['outcome']=='ALLOCATED')
    check('fresh install persistent command replay',admin.api('POST','/fulfillment/order/allocate',body,headers={'Idempotency-Key':key})==allocated)
    stock=admin.api('GET','/fulfillment/stock/get',params={'productId':f['product'],'warehouseId':f['warehouse']})
    check('fresh install H R A exact',stock['physical']=='2.000001' and stock['reserved']=='2.000000' and stock['available']=='0.000001')
    rid=allocated['reservations'][0]['id']
    released=admin.api('POST','/fulfillment/order/release',{'orderId':order,'items':[{'reservationId':rid,'quantity':'1'}],'reason':'fresh install release'},headers={'Idempotency-Key':uuid.uuid4().hex})
    check('fresh install partial release',released['status']=='WAIT_STOCK')
    check('fresh install reservation and ledger match',str(sql('SELECT held_qty FROM ful_reservation WHERE id=%s',(rid,))[0][0])=='1.000000' and str(sql('SELECT SUM(held_delta) FROM ful_stock_ledger WHERE reservation_id=%s',(rid,))[0][0])=='1.000000')
    check('fresh install all versions recorded',sql('SELECT version FROM ful_flyway_schema_history ORDER BY installed_rank')==(('0',),('1',),('2',)))
    E['result']='passed'
except Exception as exc:E['result']='failed';E['error']=str(exc);raise
finally:
    (ROOT/'../学习资料/10-验收证据/M2-clean-smoke.json').write_text(json.dumps(E,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('M2 clean smoke',E.get('result'),len(E['checks']),'checks')
