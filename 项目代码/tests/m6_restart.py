"""Full dependency restart, private file survival and original intent replay."""
import hashlib,json,os,subprocess,sys,uuid
from datetime import datetime,timezone
import m6_foundation as m
os.environ['DB_NAME']='fulfillment';m.DATABASE='fulfillment'
E={'run_at':datetime.now(timezone.utc).isoformat(),'checks':[]}
def check(name,ok,detail=None):
    E['checks'].append({'name':name,'passed':bool(ok),'detail':detail})
    if not ok:raise AssertionError(name+': '+str(detail))
def files():
    root=m.ROOT/'.local/fulfillment-files/fulfillment'
    result=[]
    for ident,key,size,sha in m.sql('SELECT id,storage_key,byte_size,sha256 FROM ful_private_file ORDER BY id'):
        path=root/key
        result.append([str(ident),key,path.stat().st_size,hashlib.sha256(path.read_bytes()).hexdigest()])
        assert result[-1][2:]==[size,sha],result[-1]
    return result
try:
    demo=json.loads((m.ROOT/'../学习资料/10-验收证据/M6-main-demo.json').read_text(encoding='utf-8'))
    ui=json.loads((m.ROOT/'../学习资料/10-验收证据/M6-browser-SQL.json').read_text(encoding='utf-8'))
    check('actual browser actions verified',ui['result']=='passed')
    c=m.Client(48080).login();scan='m6-restart-'+uuid.uuid4().hex
    report=c.api('POST','/fulfillment/reconcile/run',{'scope':'TENANT'},headers={'Idempotency-Key':scan})
    check('main business facts clean before restart',report['differenceCount']==0)
    m.wait(lambda:m.sql("SELECT COUNT(*) FROM ful_file_job WHERE status IN ('PENDING','RUNNING','RETRY_WAIT','CANCEL_REQUESTED')")[0][0]==0)
    m.wait(lambda:m.sql("SELECT COUNT(*) FROM ful_outbox_event WHERE status<>'SENT'")[0][0]==0)
    before_files=files();check('all registered private files match persisted hash before restart',len(before_files)>0)
    env=os.environ.copy();env['RESTART_EVIDENCE']='M6-restart.json'
    with (m.ROOT/'.local/m6-full-restart.log').open('wb') as out:
        r=subprocess.run([sys.executable,str(m.ROOT/'tests/m0_restart.py')],env=env,stdout=out,stderr=subprocess.STDOUT,timeout=240)
    check('full MySQL Redis RabbitMQ EPMD and applications restart exits0',r.returncode==0)
    saved=json.loads((m.ROOT/'../学习资料/10-验收证据/M6-restart.json').read_text(encoding='utf-8'))
    check('all SQL Redis and six job table snapshots exact',saved['status']=='passed' and saved['before']==saved['after'] and all(t+'_facts' in saved['before'] for t in ['ful_job_gate','ful_private_file','ful_file_job','ful_file_job_row','ful_import_identity','ful_operation_audit']))
    check('private bytes and hashes exact across restart',before_files==files())
    c=m.Client(48080).login();business=m.business()
    counts=m.sql('SELECT (SELECT COUNT(*) FROM ful_file_job),(SELECT COUNT(*) FROM ful_import_identity),(SELECT COUNT(*) FROM ful_operation_audit)')
    check('original import key stable',c.import_file(demo['file']['fileId'],demo['source'],demo['import_key'])==demo['import_result'])
    check('original export key stable',c.export('STOCK',[demo['warehouse_id']],demo['export_key'])==demo['export_result'])
    check('original intent replay creates no tasks identities audit or business writes',counts==m.sql('SELECT (SELECT COUNT(*) FROM ful_file_job),(SELECT COUNT(*) FROM ful_import_identity),(SELECT COUNT(*) FROM ful_operation_audit)') and business==m.business())
    for job,kind in [(demo['import_result']['jobId'],'ERROR'),(demo['export_result']['jobId'],'RESULT')]:
        response=c.download(job,kind);column='error_file_id' if kind=='ERROR' else 'result_file_id'
        sha=m.sql('SELECT f.sha256 FROM ful_private_file f JOIN ful_file_job j ON j.'+column+'=f.id WHERE j.id=%s',(job,))[0][0]
        check('authorized '+kind+' download survives restart',response.status_code==200 and hashlib.sha256(response.content).hexdigest()==sha)
    check('saved business report key stable',c.api('POST','/fulfillment/reconcile/run',{'scope':'TENANT'},headers={'Idempotency-Key':scan})==report)
    check('new observation still clean',c.api('POST','/fulfillment/reconcile/run',{'scope':'TENANT'},headers={'Idempotency-Key':uuid.uuid4().hex})['differenceCount']==0)
    E.update(private_files=before_files,result='passed')
except Exception as error:E['result']='failed';E['error']=str(error);raise
finally:
    (m.ROOT/'../学习资料/10-验收证据/M6-replay-after-restart.json').write_text(json.dumps(E,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
    print('M6 full restart/replay',E.get('result'),len(E['checks']),'checks',flush=True)
