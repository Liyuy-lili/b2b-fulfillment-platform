"""Verify actual browser import/retry/export/download/grant actions read-only."""
import hashlib,json,os
from datetime import datetime,timezone
import m6_foundation as m
os.environ['DB_NAME']='fulfillment'
demo=json.loads((m.ROOT/'../学习资料/10-验收证据/M6-main-demo.json').read_text(encoding='utf-8'))
E={'run_at':datetime.now(timezone.utc).isoformat(),'checks':[]}
def check(name,ok,detail=None):
    E['checks'].append({'name':name,'passed':bool(ok),'detail':detail})
    if not ok:raise AssertionError(name+': '+str(detail))
try:
    rows=m.sql("SELECT id,status,success_rows,failed_rows,total_attempts FROM ful_file_job WHERE source_system=%s AND id<>%s ORDER BY id",(demo['source'],demo['import_result']['jobId']))
    check('one real browser import task with failed-row retry',len(rows)==1 and rows[0][1:] == ('PARTIAL_FAILED',2,1,2),rows)
    job=rows[0][0];check('browser duplicate import retains two original business identities',m.sql('SELECT COUNT(*) FROM ful_import_identity WHERE source_system=%s',(demo['source'],))==((2,),) and m.sql("SELECT COUNT(*) FROM ful_file_job_row WHERE job_id=%s AND outcome='EXISTING'",(job,))==((2,),))
    check('browser retry audited with reason',m.sql("SELECT COUNT(*) FROM ful_operation_audit WHERE object_type='JOB' AND object_id=%s AND operation='JOB_RETRY' AND reason LIKE 'M6页面验收%%'",(str(job),))==((1,),))
    check('browser submitted a new completed scoped export',m.sql("SELECT COUNT(*) FROM ful_file_job WHERE job_type='EXPORT' AND id<>%s AND status='SUCCEEDED'",(demo['export_result']['jobId'],))==((1,),))
    check('browser downloaded error CSV and result XLSX with server audit',m.sql("SELECT COUNT(*) FROM ful_operation_audit WHERE operation='FILE_DOWNLOAD'")[0][0]>=demo['before_download_count']+2)
    grant=m.sql("SELECT deleted+0 FROM ful_warehouse_grant WHERE tenant_id=1 AND user_id=%s AND warehouse_id=%s AND permission_type='OPERATE'",(demo['warehouse_user_id'],demo['warehouse_id']))
    check('browser operation grant enabled then revoked with two audit records',grant==((1,),) and m.sql("SELECT COUNT(*) FROM ful_operation_audit WHERE object_type='GRANT' AND object_id=%s AND reason LIKE 'M6页面验收%%'",(demo['warehouse_user_id']+':'+demo['warehouse_id'],))==((2,),))
    check('read grant remains independent',m.sql("SELECT deleted+0 FROM ful_warehouse_grant WHERE tenant_id=1 AND user_id=%s AND warehouse_id=%s AND permission_type='READ'",(demo['warehouse_user_id'],demo['warehouse_id']))==((0,),))
    check('17 business tables identical across all browser file actions',hashlib.sha256(json.dumps(m.business(),default=str,sort_keys=True).encode()).hexdigest()==demo['before_browser_digest'])
    E.update(import_job=str(job),result='passed')
except Exception as error:E['result']='failed';E['error']=str(error);raise
finally:
    (m.ROOT/'../学习资料/10-验收证据/M6-browser-SQL.json').write_text(json.dumps(E,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8');print('M6 browser SQL',E.get('result'),len(E['checks']),'checks')
