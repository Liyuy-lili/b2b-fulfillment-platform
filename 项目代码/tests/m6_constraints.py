"""Rollback-only M6 checks in the isolated schema; no business fixture edits."""
import json,os
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
core=json.loads((ROOT/'../学习资料/10-验收证据/M6-acceptance.json').read_text(encoding='utf-8'))
os.environ['DB_NAME']=core['database']
from m1_acceptance import sql,db
E={'run_at':datetime.now(timezone.utc).isoformat(),'database':core['database'],'checks':[]}
def check(name,ok,detail=None):
    E['checks'].append({'name':name,'passed':bool(ok),'detail':detail})
    if not ok:raise AssertionError(name+': '+str(detail))
try:
    check('only passed isolated M6 schema',core['result']=='passed' and core['database'].startswith('fulfillment_m6_'))
    job=sql('SELECT id FROM ful_file_job ORDER BY id LIMIT 1')[0][0];row=sql('SELECT id FROM ful_file_job_row ORDER BY id LIMIT 1')[0][0];file=sql('SELECT id FROM ful_private_file ORDER BY id LIMIT 1')[0][0];grant=sql('SELECT id FROM ful_warehouse_grant ORDER BY id LIMIT 1')[0][0]
    tables=['ful_job_gate','ful_private_file','ful_file_job','ful_file_job_row','ful_import_identity','ful_operation_audit','ful_warehouse_grant'];before={t:sql('SELECT * FROM '+t+' ORDER BY '+('tenant_id' if t=='ful_job_gate' else 'id')) for t in tables}
    probes=[('job invalid state',"UPDATE ful_file_job SET status='DONE' WHERE id=%s",(job,),3819),('job negative success','UPDATE ful_file_job SET success_rows=-1 WHERE id=%s',(job,),3819),('job malformed scope',"UPDATE ful_file_job SET scope_json='bad' WHERE id=%s",(job,),3819),('row foreign tenant FK','UPDATE ful_file_job_row SET tenant_id=999999 WHERE id=%s',(row,),1452),('row invalid state',"UPDATE ful_file_job_row SET status='RUNNING' WHERE id=%s",(row,),3819),('row malformed JSON',"UPDATE ful_file_job_row SET raw_json='broken' WHERE id=%s",(row,),3819),('file negative byte size','UPDATE ful_private_file SET byte_size=-1 WHERE id=%s',(file,),3819),('warehouse permission CHECK',"UPDATE ful_warehouse_grant SET permission_type='ADMIN' WHERE id=%s",(grant,),3819)]
    for name,query,args,expected in probes:
        code=None
        with db() as con:
            con.autocommit(False)
            try:
                with con.cursor() as cur:cur.execute(query,args)
            except Exception as error:code=error.args[0]
            finally:con.rollback()
        check('database rejects '+name,code==expected,{'actual':code,'expected':expected})
    check('all M6 facts unchanged after constraint probes',before=={t:sql('SELECT * FROM '+t+' ORDER BY '+('tenant_id' if t=='ful_job_gate' else 'id')) for t in tables})
    E['result']='passed'
except Exception as error:E['result']='failed';E['error']=str(error);raise
finally:
    (ROOT/'../学习资料/10-验收证据/M6-constraints.json').write_text(json.dumps(E,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print('M6 constraints',E.get('result'),len(E['checks']),'checks')
