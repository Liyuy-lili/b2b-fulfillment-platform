"""Negative FK/CHECK/unique probes in the labelled isolated return test DB.
Every attempted write is inside an explicitly rolled back transaction.
"""
import json,os
from datetime import datetime,timezone
from m1_acceptance import ROOT,db,sql
core=json.loads((ROOT/'../学习资料/10-验收证据/M4.2-return-acceptance.json').read_text(encoding='utf-8'))
assert core['database'].startswith('fulfillment_m4_return_')
os.environ['DB_NAME']=core['database']
E={'run_at':datetime.now(timezone.utc).isoformat(),'database':core['database'],'checks':[]}
def probe(name,query,parameters,code):
    with db() as connection:
        connection.begin()
        try:
            try:
                with connection.cursor() as cursor:cursor.execute(query,parameters)
            except Exception as error:actual=error.args[0]
            else:actual=0
        finally:connection.rollback()
    E['checks'].append({'name':name,'passed':actual==code,'mysql_error':actual,'expected':code})
    if actual!=code:raise AssertionError(name+': '+str(actual))
try:
    fx=core['ids']['精度闭环'];other=core['ids']['并发申请']
    received=sql("SELECT id,erp_sale_return_id FROM ful_return WHERE tenant_id=1 AND status='RECEIVED' ORDER BY id LIMIT 2")
    rows=sql('SELECT id,erp_stock_record_id FROM ful_return_item WHERE tenant_id=1 AND erp_stock_record_id IS NOT NULL ORDER BY id LIMIT 2')
    rejected=sql("SELECT id FROM ful_return WHERE tenant_id=1 AND status='REJECTED' ORDER BY id LIMIT 1")[0][0]
    tenant=sql('SELECT tenant_id FROM ful_order WHERE id=%s',(core['ids']['外租户退回']['order'],))[0][0]
    before=sql('SELECT id,status,erp_sale_return_id,rejection_reason FROM ful_return ORDER BY id'),sql('SELECT id,quantity,erp_stock_record_id,shipment_item_id,tenant_id FROM ful_return_item ORDER BY id')
    probe('same original shipment item identity enforced','UPDATE ful_return_item SET shipment_item_id=%s WHERE id=%s',(other['lines'][0]['id'],rows[0][0]),1452)
    probe('original warehouse enforced','UPDATE ful_return SET warehouse_id=999999 WHERE id=%s',(received[0][0],),1452)
    probe('same tenant association enforced','UPDATE ful_return_item SET tenant_id=%s WHERE id=%s',(tenant,rows[0][0]),1452)
    probe('received state requires its timestamp','UPDATE ful_return SET received_at=NULL WHERE id=%s',(received[0][0],),3819)
    probe('rejected reason cannot be null','UPDATE ful_return SET rejection_reason=NULL WHERE id=%s',(rejected,),3819)
    probe('fact quantity must be positive','UPDATE ful_return_item SET quantity=0 WHERE id=%s',(rows[0][0],),3819)
    probe('return facts cannot be soft deleted','UPDATE ful_return SET deleted=1 WHERE id=%s',(received[0][0],),3819)
    probe('ERP receipt header mapping unique','UPDATE ful_return SET erp_sale_return_id=%s WHERE id=%s',(received[0][1],received[1][0]),1062)
    probe('physical record mapping unique','UPDATE ful_return_item SET erp_stock_record_id=%s WHERE id=%s',(rows[0][1],rows[1][0]),1062)
    after=sql('SELECT id,status,erp_sale_return_id,rejection_reason FROM ful_return ORDER BY id'),sql('SELECT id,quantity,erp_stock_record_id,shipment_item_id,tenant_id FROM ful_return_item ORDER BY id')
    E['checks'].append({'name':'all probes rolled back with facts unchanged','passed':before==after})
    if before!=after:raise AssertionError('negative probes changed facts')
    E['result']='passed'
except Exception as error:E['result']='failed';E['error']=str(error);raise
finally:
    (ROOT/'../学习资料/10-验收证据/M4.2-constraints.json').write_text(json.dumps(E,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('M4.2 constraints',E.get('result'),len(E['checks']),'checks')
