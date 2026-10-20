"""Main M5 demo via real APIs; read-only SQL records pre-browser facts."""
import hashlib,json,os,time
from datetime import datetime,timezone
import m5_acceptance as m
os.environ['DB_NAME']='fulfillment';m.DATABASE=m.VHOST='fulfillment'
E={'run_at':datetime.now(timezone.utc).isoformat(),'checks':[]}
def check(name,ok,detail=None):
    E['checks'].append({'name':name,'passed':bool(ok),'detail':detail})
    if not ok:raise AssertionError(name+': '+str(detail))
def digest():return hashlib.sha256(json.dumps(m.facts(),default=str,sort_keys=True).encode()).hexdigest()
try:
    check('main V6 installed',m.sql('SELECT MAX(CAST(version AS UNSIGNED)) FROM ful_flyway_schema_history')[0][0]==6)
    c=m.Client(48080).login();f=m.b.Fixture(c,'MainDemo');fx=f.shipment('消息演示',('1',),ordered='3')
    ret=c.create_return(fx['order'],fx['shipment'],[(fx['lines'][0]['id'],'1')]);c.receive(fx['order'],ret['id'])
    m.wait(lambda:m.sql("SELECT COUNT(*) FROM ful_outbox_event e LEFT JOIN ful_inbox_event i ON i.tenant_id=e.tenant_id AND i.event_id=e.event_id WHERE e.order_id=%s AND e.status='SENT' AND i.status='PROCESSED'",(fx['order'],))[0][0]==5)
    check('five real new events completed',m.sql('SELECT COUNT(*) FROM ful_outbox_event WHERE order_id=%s',(fx['order'],))[0][0]==5)
    ev=m.event_for(fx['order'],'SHIPMENT_CONFIRMED')[0];detail=c.api('GET','/fulfillment/order/get',params={'id':fx['order']})
    E.update(fixture=fx,return_id=ret['id'],order_no=detail['orderNo'],event_id=ev,before_browser_digest=digest())
    check('H20 R0 shipped1 returned1 cancelled2',m.sql('SELECT `count` FROM erp_stock WHERE product_id=%s AND warehouse_id=%s',(fx['product'],fx['warehouse']))[0][0]==20 and all(detail['items'][0][k]==v for k,v in {'reservedQty':'0.000000','shippedQty':'1.000000','returnedQty':'1.000000','cancelledQty':'2.000000'}.items()))
    check('read model version aligned',m.sql('SELECT m.observed_version=o.version FROM ful_order o JOIN ful_order_read_model m ON m.tenant_id=o.tenant_id AND m.order_id=o.id WHERE o.id=%s',(fx['order'],))==((1,),))
    E['result']='passed'
except Exception as error:E['result']='failed';E['error']=str(error);raise
finally:
    (m.ROOT/'../学习资料/10-验收证据/M5-main-demo.json').write_text(json.dumps(E,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
    print(json.dumps(E,ensure_ascii=False,default=str),flush=True)
