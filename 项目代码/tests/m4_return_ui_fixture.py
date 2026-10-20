"""Create a labelled main-demo shipment via HTTP for real browser return actions.
No return is created/received by this setup. Does not change historical M3 fixtures.
"""
import json,os,time
from datetime import datetime,timezone
os.environ['M4_RETURN_DATABASE']='fulfillment'
import m4_return_acceptance as base
from m1_acceptance import ROOT
for attempt in range(60):
    try:admin=base.Client(48080).login();break
    except Exception:time.sleep(.5)
else:raise RuntimeError('main application not ready')
fixture=base.Fixture(admin,'DEMO').shipment('浏览器退货演示',('6',),ordered='10')
fixture['orderNo']=admin.api('GET','/fulfillment/order/get',params={'id':fixture['order']})['orderNo']
fixture['run_at']=datetime.now(timezone.utc).isoformat()
fixture['before']={'stock':base.balance(fixture),'items':base.amounts(fixture)}
(ROOT/'../学习资料/10-验收证据/M4.2-ui-fixture.json').write_text(json.dumps(fixture,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
print(json.dumps(fixture,ensure_ascii=False,default=str))
