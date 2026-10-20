"""One-shot continuation: await current gates, measure, upgrade, restart, release.
Stops at real browser proof; --from selects a failed/later stage without rerunning
the one-time upgrade. This is an active task helper, not a recurring automation.
"""
import argparse,os,subprocess,sys,time
from datetime import datetime,timezone
import m7_support as h
parser=argparse.ArgumentParser();parser.add_argument('--from',dest='first',choices=['query','stock','upgrade','restart','release'],default='query');parser.add_argument('--await-retry',action='store_true');args=parser.parse_args();started=time.time()
E={'run_at':datetime.now(timezone.utc).isoformat(),'artifact_sha256':h.sha(h.JAR),'first':args.first,'await_retry':args.await_retry,'stages':[]}
try:
    until=time.monotonic()+3600
    while True:
        ready=True
        for c in ['core','expiry','returns','reconcile','message','filefoundation','file']:
            p=h.OUT/('M7.2-'+c+'-run.json')
            if not p.exists():ready=False;continue
            try:v=h.load(p.name)
            except ValueError:ready=False;continue
            if v['result']!='passed' and args.await_retry and p.stat().st_mtime<started:ready=False;continue
            assert v['result']=='passed',(c,v.get('error'));assert v['artifact_sha256']==E['artifact_sha256']
        if ready:break
        assert time.monotonic()<until,'Timed out awaiting current regression gates';time.sleep(2)
    assert all(h.free(p) for p in [48082,48083,48084,48085])
    stages=[('query','m7_query_benchmark.py'),('stock','m7_stock_benchmark.py'),('upgrade','m7_main_upgrade.py'),('restart','m7_main_restart.py'),('release','m7_release.py')]
    start=next(n for n,x in enumerate(stages) if x[0]==args.first)
    for label,script in stages[start:]:
        env=os.environ.copy();env['M0_PWSH']='pwsh'
        if label=='release':env.update(M7_DELIVERY_PREFIX='M7-final',M7_DELIVERY_REDIS='13')
        log=h.ROOT/'.local'/('m7-'+label+'-run.log');print('M7_START '+label,flush=True);t=time.monotonic()
        with log.open('wb') as out:r=subprocess.run([sys.executable,str(h.ROOT/'tests'/script)],cwd=h.ROOT,env=env,stdout=out,stderr=subprocess.STDOUT)
        E['stages'].append({'stage':label,'script':script,'exit_code':r.returncode,'seconds':time.monotonic()-t,'log':str(log.relative_to(h.ROOT)),'log_sha256':h.sha(log)});h.save('M7-runtime-pipeline.json',E)
        assert r.returncode==0,label+' failed: '+str(log)
        print('M7_DONE '+label,flush=True)
    E['result']='ready_for_browser';print('M7_READY_FOR_BROWSER',flush=True)
except Exception as error:E.update(result='failed',error=str(error));raise
finally:h.save('M7-runtime-pipeline.json',E)
