"""Rollback-only FK/CHECK probes in the isolated M4.3 database."""
import json,os
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
core=json.loads((ROOT/'../学习资料/10-验收证据/M4.3-reconcile-acceptance.json').read_text(encoding='utf-8'))
os.environ['DB_NAME']=core['database']
from m1_acceptance import db,sql
E={'run_at':datetime.now(timezone.utc).isoformat(),'database':core['database'],'checks':[]}
def check(name,ok,detail=None):
    E['checks'].append({'name':name,'passed':bool(ok),'detail':detail})
    if not ok:raise AssertionError(name+': '+str(detail))
try:
    check('only passed isolated schema',core['result']=='passed' and core['database'].startswith('fulfillment_m4_reconcile_'))
    item=sql('SELECT id FROM ful_reconcile_item ORDER BY id LIMIT 1')[0][0]
    review=sql('SELECT id FROM ful_reconcile_review ORDER BY id LIMIT 1')[0][0]
    run=core['clean']['id']
    before={t:sql('SELECT * FROM '+t+' ORDER BY id') for t in ['ful_reconcile_run','ful_reconcile_item','ful_reconcile_review']}
    probes=[('tenant FK','UPDATE ful_reconcile_item SET tenant_id=999999 WHERE id=%s',(item,),1452),
            ('review same-run FK','UPDATE ful_reconcile_review SET run_id=%s WHERE id=%s',(run,review),1452),
            ('confirmation status CHECK',"UPDATE ful_reconcile_item SET resolution_status='FIXED' WHERE id=%s",(item,),3819),
            ('empty note CHECK',"UPDATE ful_reconcile_review SET note='' WHERE id=%s",(review,),3819),
            ('difference limit CHECK','UPDATE ful_reconcile_run SET difference_count=2001 WHERE id=%s',(run,),3819),
            ('scope CHECK',"UPDATE ful_reconcile_run SET scope='ORDER' WHERE id=%s",(run,),3819)]
    for name,query,args,expected in probes:
        code=None
        with db() as con:
            con.autocommit(False)
            try:
                with con.cursor() as cur:cur.execute(query,args)
            except Exception as error:code=error.args[0]
            finally:con.rollback()
        check('database rejects '+name,code==expected,{'actual':code,'expected':expected})
    check('all report and review facts unchanged',before=={t:sql('SELECT * FROM '+t+' ORDER BY id') for t in before})
    E['result']='passed'
except Exception as error:E['result']='failed';E['error']=str(error);raise
finally:
    (ROOT/'../学习资料/10-验收证据/M4.3-constraints.json').write_text(json.dumps(E,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('M4.3 constraints',E.get('result'),len(E['checks']),'checks')
