"""Full main dependency restart, immutable report replay and read-only business invariants."""
import json,os,subprocess,sys,uuid
from datetime import datetime,timezone
from m1_acceptance import ROOT,sql
from m3_acceptance import M3Client
E={'run_at':datetime.now(timezone.utc).isoformat(),'checks':[]}
def check(name,ok,detail=None):
    E['checks'].append({'name':name,'passed':bool(ok),'detail':detail})
    if not ok:raise AssertionError(name+': '+str(detail))
def scan(c,key):return c.api('POST','/fulfillment/reconcile/run',{'scope':'TENANT'},headers={'Idempotency-Key':key})
try:
    c=M3Client().login();key='restart-reconcile-'+uuid.uuid4().hex
    report=scan(c,key);check('pre-restart main report clean',report['differenceCount']==0,report)
    E['idempotency_key']=key;E['report']=report
    env=os.environ.copy();env['RESTART_EVIDENCE']='M4.3-restart.json'
    with (ROOT/'.local/m4-reconcile-restart.log').open('wb') as out:r=subprocess.run([sys.executable,str(ROOT/'tests/m0_restart.py')],env=env,stdout=out,stderr=subprocess.STDOUT,timeout=220)
    check('full dependency restart exits0',r.returncode==0)
    saved=json.loads((ROOT/'../学习资料/10-验收证据/M4.3-restart.json').read_text(encoding='utf-8'));check('full snapshots including reports equal',saved['status']=='passed' and saved['before']==saved['after'])
    c=M3Client().login();count=sql('SELECT COUNT(*) FROM ful_reconcile_run')[0][0]
    check('same run key survives complete dependency restart',scan(c,key)==report)
    check('replay creates no extra report',sql('SELECT COUNT(*) FROM ful_reconcile_run')[0][0]==count)
    check('saved get still exact',c.api('GET','/fulfillment/reconcile/get',params={'id':report['id']})==report)
    check('new key scans current main clean facts',scan(c,'new-'+key)['differenceCount']==0)
    E['result']='passed'
except Exception as error:E['result']='failed';E['error']=str(error);raise
finally:
    (ROOT/'../学习资料/10-验收证据/M4.3-replay-after-restart.json').write_text(json.dumps(E,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('M4.3 restart',E.get('result'),len(E['checks']),'checks')
