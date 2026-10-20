"""Read-only SQL assertions after actual browser actions, one named stage at a time."""
import json,sys
from datetime import datetime,timezone
from decimal import Decimal as D
from m1_acceptance import ROOT,sql
stage=sys.argv[1]
if stage not in ['requested','received','rejected']:raise ValueError('named browser stage required')
fixture=json.loads((ROOT/'../学习资料/10-验收证据/M4.2-ui-fixture.json').read_text(encoding='utf-8'))
target=ROOT/'../学习资料/10-验收证据/M4.2-ui-result.json'
E=json.loads(target.read_text(encoding='utf-8')) if target.exists() else {'order':fixture['order'],'checks':[],'stages':{}}
checks=[]
def check(name,ok,detail=None):
    checks.append({'name':stage+': '+name,'passed':bool(ok),'detail':detail})
    if not ok:raise AssertionError(name+': '+str(detail))
try:
    stock=sql('SELECT `count`,ful_reserved_count FROM erp_stock WHERE tenant_id=1 AND product_id=%s AND warehouse_id=%s',(fixture['product'],fixture['warehouse']))
    items=sql('SELECT open_qty,reserved_qty,shipped_qty,cancelled_qty,returned_qty FROM ful_order_item WHERE order_id=%s',(fixture['order'],))
    heads=sql('SELECT id,status,erp_sale_return_id,reason,rejection_reason FROM ful_return WHERE order_id=%s ORDER BY id',(fixture['order'],))
    expected_h=D(14) if stage=='requested' else D(16);expected_return=D(0) if stage=='requested' else D(2)
    check('physical increases only on actual receipt',stock==((expected_h,D(0)),),stock)
    check('gross shipped and cancelled preserved, returned separate',items==((D(0),D(0),D(6),D(4),expected_return),),items)
    statuses=['REQUESTED'] if stage=='requested' else ['RECEIVED'] if stage=='received' else ['RECEIVED','REJECTED']
    check('exact expected application states',[r[1] for r in heads]==statuses,heads)
    check('no automatic order reopening',sql('SELECT status FROM ful_order WHERE id=%s',(fixture['order'],))[0][0]=='PARTIALLY_CLOSED')
    changes=sql('SELECT `count` FROM erp_stock_record WHERE tenant_id=1 AND product_id=%s AND biz_type=60 ORDER BY id',(fixture['product'],))
    check('one ERP physical receipt effect',changes==(() if stage=='requested' else ((D(2),),)),changes)
    if stage!='requested':
        check('ERP source out stays gross and return increases once',sql('SELECT out_count,return_count FROM erp_sale_order_items WHERE order_id=%s',(fixture['source'],))==((D(6),D(2)),))
        check('ERP physical mapping in original warehouse',sql("SELECT ri.quantity,ei.`count`,ei.warehouse_id,s.`count`,s.biz_type FROM ful_return_item ri JOIN ful_return r ON r.id=ri.return_id JOIN erp_sale_return_items ei ON ei.id=ri.erp_sale_return_item_id JOIN erp_stock_record s ON s.id=ri.erp_stock_record_id WHERE r.order_id=%s AND r.status='RECEIVED'",(fixture['order'],))==((D(2),D(2),fixture['warehouse'],D(2),60),))
        check('goods return does not create refund',sql('SELECT refund_price FROM erp_sale_return WHERE id=%s',(heads[0][2],))[0][0]==0)
    E['stages'][stage]={'run_at':datetime.now(timezone.utc).isoformat(),'stock':stock,'items':items,'heads':heads}
    E['result']='passed'
except Exception as error:E['result']='failed';E['error']=str(error);raise
finally:
    E['checks'].extend(checks);target.write_text(json.dumps(E,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
    print('M4.2 browser SQL',stage,E.get('result'),len(checks),'checks')
