"""Inject a failure inside ERP approval, after physical effects, through an isolated test-only aspect."""
import json,uuid
from datetime import datetime,timezone
from m3_acceptance import M3Client
from m2_acceptance import balance
from m1_acceptance import ROOT,sql
E={'run_at':datetime.now(timezone.utc).isoformat(),'checks':[]};RUN='M3F'+uuid.uuid4().hex[:7];NOW=datetime.now().isoformat(timespec='seconds')
def check(name,ok,detail=None):
    E['checks'].append({'name':name,'passed':bool(ok),'detail':detail})
    if not ok:raise AssertionError(name+': '+str(detail))
def main():
    admin=M3Client().login();fault=M3Client(48083).login();f=json.loads((ROOT/'../学习资料/10-验收证据/M2-acceptance.json').read_text(encoding='utf-8'))['ids']
    p=admin.create('product',{'name':RUN,'barCode':RUN,'categoryId':f['category'],'unitId':f['unit'],'status':0,'salePrice':'0'})
    incoming=admin.create('stock-in',{'supplierId':f['supplier'],'inTime':NOW,'items':[{'productId':p,'warehouseId':f['warehouse_a'],'count':'6','productPrice':'0'}]});admin.approve('stock-in',incoming)
    source=admin.create('sale-order',{'customerId':f['customer'],'accountId':f['account'],'orderTime':NOW,'discountPercent':'0','items':[{'productId':p,'productPrice':'0','count':'4','taxPercent':'0'}]});admin.approve('sale-order',source);order=admin.bind(source)['orderId'];reservation=admin.allocate(order,[f['warehouse_a']])['reservations'][0]['id'];key='during-'+RUN
    def facts():
        return {'balance':balance(p,f['warehouse_a']),'quantity':sql('SELECT open_qty,reserved_qty,shipped_qty,cancelled_qty FROM ful_order_item WHERE order_id=%s',(order,)),
                'reservation':sql('SELECT held_qty,consumed_qty,released_qty FROM ful_reservation WHERE id=%s',(reservation,)),
                'erp_out':sql('SELECT id,status FROM erp_sale_out WHERE order_id=%s',(source,)),
                'erp_ledger':sql('SELECT id,`count` FROM erp_stock_record WHERE product_id=%s',(p,)),
                'ful_ledger':sql('SELECT id,held_delta FROM ful_stock_ledger WHERE product_id=%s',(p,)),
                'source_out':sql('SELECT out_count FROM erp_sale_order WHERE id=%s',(source,))}
    before=facts();response=fault.ship(order,f['warehouse_a'],[(reservation,'2')],key,ok=False)
    check('ERP approval fault returned failure',response['code']==500,response)
    trace=(ROOT/'.local/m3-fault-out.log').read_text(encoding='utf-8',errors='replace')
    check('failure occurred during stock batch inside ERP approval','M3_TEST_FAILURE_DURING_ERP_APPROVAL' in trace)
    E['fault_trace']=[line for line in trace.splitlines() if 'M3_TEST_FAILURE_DURING_ERP_APPROVAL' in line][:3]
    check('all database business facts rolled back',facts()==before)
    check('failed command row rolled back',not sql('SELECT id FROM ful_command_record WHERE idempotency_key=%s',(key,)))
    check('failed shipment row absent',not sql('SELECT id FROM ful_shipment WHERE order_id=%s',(order,)))
    recovered=admin.ship(order,f['warehouse_a'],[(reservation,'2')],key)
    check('same key safe to retry on healthy instance',balance(p,f['warehouse_a'])==(4,2) and recovered['orderStatus']=='PARTIALLY_SHIPPED')
    check('recovered command does not double ship',admin.ship(order,f['warehouse_a'],[(reservation,'2')],key)==recovered and balance(p,f['warehouse_a'])==(4,2))
    E['ids']={'order':order,'source':source,'reservation':reservation,'shipment':recovered};E['result']='passed'
if __name__=='__main__':
    try:main()
    except Exception as exc:E['result']='failed';E['error']=str(exc);raise
    finally:
        (ROOT/'../学习资料/10-验收证据/M3-erp-approval-failure.json').write_text(json.dumps(E,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
        print('M3 ERP failure',E.get('result'),len(E['checks']),'checks')
