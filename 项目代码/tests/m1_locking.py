"""Deterministic MySQL lock interleavings. The local project root only reads
database session metadata; business fixtures use real HTTP APIs.
Run after m1_acceptance.py while no unrelated project writes run.
"""
import concurrent.futures,json,time,uuid,os
from datetime import datetime,timezone
import pymysql
from m1_acceptance import Client,ROOT,db,sql

E={'run_at':datetime.now(timezone.utc).isoformat(),'checks':[],'interleavings':[]}
def check(name,ok,detail=None):
    E['checks'].append({'name':name,'passed':bool(ok),'detail':detail})
    if not ok:raise AssertionError(name+': '+str(detail))
def main():
    fixture=json.loads((ROOT/'../学习资料/10-验收证据/M1-acceptance.json').read_text(encoding='utf-8'))['ids']
    admin=Client().login();now=datetime.now().isoformat(timespec='seconds')
    line={'productId':fixture['product'],'count':'1','productPrice':'12.5','taxPercent':'0'}
    def order():
        ident=admin.create('sale-order',{'customerId':fixture['customer'],'accountId':fixture['account'],'orderTime':now,'discountPercent':'0','items':[line]})
        admin.approve('sale-order',ident);return ident
    def out_body(source):
        item=admin.api('GET','/erp/sale-order/get',params={'id':source})['items'][0]
        return {'orderId':source,'accountId':fixture['account'],'outTime':now,'discountPercent':'0','otherPrice':'0',
                'items':[dict(line,orderItemId=item['id'],warehouseId=fixture['warehouse'])]}
    def client():
        c=Client();c.s.headers.update(admin.s.headers);return c
    with pymysql.connect(host='127.0.0.1',port=33306,user='root',password='local-root-dev',autocommit=True) as monitor:
        def wait_for(n):
            deadline=time.monotonic()+8
            while time.monotonic()<deadline:
                with monitor.cursor() as cur:
                    # MySQL may wait during plan statistics before exposing an
                    # innodb_trx row. Observe the actual outstanding source-lock
                    # statements instead, while this test holds their source row.
                    cur.execute('SHOW FULL PROCESSLIST')
                    waits=[(r[0],r[6],r[7]) for r in cur.fetchall() if r[3]=='fulfillment'
                           and r[4]=='Query' and r[7] and 'FROM erp_sale_order WHERE' in r[7]
                           and 'FOR UPDATE' in r[7]]
                if len(waits)>=n:
                    E['interleavings'].append({'expected_waiters':n,'observed_waiters':waits});return
                time.sleep(.04)
            with monitor.cursor() as cur:
                cur.execute('SELECT trx_mysql_thread_id,trx_state,trx_query FROM information_schema.innodb_trx')
                E['timeout_transactions']=cur.fetchall()
                cur.execute('SHOW FULL PROCESSLIST');E['timeout_processes']=cur.fetchall()
            raise AssertionError('Required lock interleaving was not reached')

        # Two writers both read the original document before waiting. One moves
        # its parent; the loser must re-read and reject, rather than writing
        # under locks for the wrong parent.
        old=order();new1=order();new2=order();document=admin.create('sale-out',out_body(old))
        body1=dict(out_body(new1),id=document);body2=dict(out_body(new2),id=document)
        with db() as hold:
            hold.begin()
            with hold.cursor() as cur:cur.execute('SELECT id FROM erp_sale_order WHERE id=%s FOR UPDATE',(old,))
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                a=pool.submit(client().api,'PUT','/erp/sale-out/update',body1,ok=False)
                b=pool.submit(client().api,'PUT','/erp/sale-out/update',body2,ok=False)
                try:wait_for(2)
                finally:hold.rollback()
                results=[a.result(),b.result()]
        check('changed parent writer is rejected',sorted(r['code'] for r in results)==[0,1030199001],results)
        current=admin.api('GET','/erp/sale-out/get',params={'id':document})
        check('exactly one target owns document',current['orderId'] in [new1,new2])
        counts=sql('SELECT id,out_count FROM erp_sale_order WHERE id IN (%s,%s,%s) ORDER BY id',(old,new1,new2))
        check('old parent count restored and only one new parent incremented',str(counts[0][1])=='0.000000' and sum(r[1] for r in counts)==1,[(i,str(c)) for i,c in counts])

        # Binding queues before a legacy document update. The old transaction
        # already read the document before waiting. A current policy read still
        # must observe the newly committed fulfillment row. The project datasource
        # is RC, verified by the startup guard (RR gap-lock regression was found here).
        existing_source=order();target=order();document=admin.create('sale-out',out_body(existing_source))
        update=dict(out_body(target),id=document)
        with db() as hold:
            hold.begin()
            with hold.cursor() as cur:cur.execute('SELECT id FROM erp_sale_order WHERE id=%s FOR UPDATE',(target,))
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                a=pool.submit(client().bind,target,'locking'+uuid.uuid4().hex,False)
                try:
                    wait_for(1)
                    b=pool.submit(client().api,'PUT','/erp/sale-out/update',update,ok=False)
                    wait_for(2)
                finally:hold.rollback()
                bound,changed=a.result(),b.result()
        check('binding wins committed source lock',bound['code']==0,bound)
        check('waiting legacy transaction sees newly managed row',changed['code']==1030199000,changed)
        check('rejected document move remains on original source',admin.api('GET','/erp/sale-out/get',params={'id':document})['orderId']==existing_source)
    E['result']='passed'

if __name__=='__main__':
    try:main()
    except Exception as exc:E['result']='failed';E['error']=str(exc);raise
    finally:
        (ROOT/'../学习资料/10-验收证据'/os.getenv('M1_LOCK_EVIDENCE','M1-locking.json')).write_text(json.dumps(E,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
        print('M1 locking',E.get('result'),len(E['checks']),'checks')
