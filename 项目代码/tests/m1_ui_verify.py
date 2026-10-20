"""SQL/HTTP verification after the separately recorded real browser binding.
Does not claim to drive the browser; screenshots and route check are in M1 UI review.
"""
import json
from datetime import datetime,timezone
from decimal import Decimal
from m1_acceptance import Client,ROOT,sql

fixture=json.loads((ROOT/'../学习资料/10-验收证据/M1-ui-fixture.json').read_text(encoding='utf-8'))
E={'run_at':datetime.now(timezone.utc).isoformat(),'fixture':fixture,'checks':[]}
def check(name,ok):
    E['checks'].append({'name':name,'passed':bool(ok)})
    if not ok:raise AssertionError(name)
try:
    source=fixture['source']
    row=sql('SELECT id,tenant_id,status FROM ful_order WHERE erp_order_id=%s',(source,))
    check('one browser-bound source snapshot',len(row)==1 and row[0][1]==1 and row[0][2]=='NEW')
    admin=Client().login()
    detail=admin.api('GET','/fulfillment/order/get',params={'id':row[0][0]})
    E['detail']=detail
    check('exact browser snapshot quantity',detail['items'][0]['orderedQty']==fixture['quantity'] and detail['items'][0]['openQty']==fixture['quantity'])
    product=detail['items'][0]['productId']
    check('no physical inventory record generated',sql('SELECT COUNT(*) FROM erp_stock_record WHERE tenant_id=1 AND product_id=%s',(product,))[0][0]==0)
    check('no physical inventory balance generated',sql('SELECT COALESCE(SUM(`count`),0) FROM erp_stock WHERE tenant_id=1 AND product_id=%s',(product,))[0][0]==Decimal(0))
    check('browser source freezes old unaudit',admin.approve('sale-order',source,10,ok=False)['code']==1030199000)
    check('source still approved',sql('SELECT status FROM erp_sale_order WHERE id=%s',(source,))[0][0]==20)
    E['result']='passed'
except Exception as exc:E['result']='failed';E['error']=str(exc);raise
finally:
    (ROOT/'../学习资料/10-验收证据/M1-ui-result.json').write_text(json.dumps(E,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('M1 UI facts',E.get('result'),len(E['checks']),'checks')
