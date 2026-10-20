"""One-time V6 -> V7 upgrade on the stopped main demo. Preserves all old facts.
Refuses any other starting version; use normal migrate/validate for later runs.
"""
import hashlib,json,os,socket,subprocess
from datetime import datetime,timezone
from m1_acceptance import ROOT,sql
from m0_restart import snapshot
E={'run_at':datetime.now(timezone.utc).isoformat(),'checks':[],'commands':[]}
def check(name,ok,detail=None):
    E['checks'].append({'name':name,'passed':bool(ok),'detail':detail})
    if not ok:raise AssertionError(name+': '+str(detail))
try:
    core=json.loads((ROOT/'../学习资料/10-验收证据/M6-acceptance.json').read_text(encoding='utf-8'))
    check('isolated M6 core passed first',core['result']=='passed')
    with socket.socket() as s:check('main application stopped before upgrade',s.connect_ex(('127.0.0.1',48080))!=0)
    versions=sql('SELECT version FROM ful_flyway_schema_history ORDER BY installed_rank')
    check('one-time starting history V0 through V6',versions==(('0',),('1',),('2',),('3',),('4',),('5',),('6',)))
    previous={x['path']:x['sha256'] for x in json.loads((ROOT/'../学习资料/10-验收证据/M4.1-changes.json').read_text(encoding='utf-8'))['files']}
    # M4.1 had no migration edits; use the M3 inventory for immutable V1-V3 hashes.
    previous.update({x['path']:x['sha256'] for x in json.loads((ROOT/'../学习资料/10-验收证据/M3-changes.json').read_text(encoding='utf-8'))['files'] if '/db/fulfillment/' in x['path']})
    for v in [1,2,3]:
        path=next((ROOT/'backend/yudao-module-fulfillment/src/main/resources/db/fulfillment').glob('V'+str(v)+'__*.sql'))
        check('V'+str(v)+' unchanged',hashlib.sha256(path.read_bytes()).hexdigest()==previous[os.path.relpath(path,ROOT).replace(chr(92),"/")])
    v4=ROOT/'backend/yudao-module-fulfillment/src/main/resources/db/fulfillment/V4__return_receipt.sql'
    locked={x['path']:x['sha256'] for x in json.loads((ROOT/'../学习资料/10-验收证据/M4.2-changes.json').read_text(encoding='utf-8'))['files']}
    check('V4 unchanged',hashlib.sha256(v4.read_bytes()).hexdigest()==locked[os.path.relpath(v4,ROOT).replace(chr(92),"/")])
    v5=ROOT/'backend/yudao-module-fulfillment/src/main/resources/db/fulfillment/V5__reconciliation.sql'
    v5locked={x['path']:x['sha256'] for x in json.loads((ROOT/'../学习资料/10-验收证据/M4.3-changes.json').read_text(encoding='utf-8'))['files']}
    check('V5 unchanged',hashlib.sha256(v5.read_bytes()).hexdigest()==v5locked[os.path.relpath(v5,ROOT).replace(chr(92),"/")])
    v6=ROOT/'backend/yudao-module-fulfillment/src/main/resources/db/fulfillment/V6__reliable_messages.sql'
    locked6={x['path']:x['sha256'] for x in json.loads((ROOT/'../学习资料/10-验收证据/M5-changes.json').read_text(encoding='utf-8'))['files']}
    check('V6 unchanged',hashlib.sha256(v6.read_bytes()).hexdigest()==locked6[os.path.relpath(v6,ROOT).replace(chr(92),"/")])
    E['before']=snapshot()
    for action in ['migrate','validate']:
        path=ROOT/'.local'/('m6-main-'+action+'.log')
        with path.open('wb') as out:r=subprocess.run([os.environ['M0_PWSH'],'-NoProfile','-File',str(ROOT/'scripts/Migrate-Database.ps1'),'-Action',action],cwd=ROOT,stdout=out,stderr=subprocess.STDOUT,timeout=120)
        E['commands'].append({'action':action,'exit_code':r.returncode,'log':str(path.relative_to(ROOT))});check(action+' exit0',r.returncode==0)
    E['after']=snapshot()
    for key,value in E['before'].items():
        if key=='fulfillment_counts':
            check('old business counts preserved',all(E['after'][key][table]==count for table,count in value.items() if table!='ful_flyway_schema_history'))
        else:check('old facts preserved '+key,E['after'].get(key)==value)
    check('main history now V0 to V7',sql('SELECT version FROM ful_flyway_schema_history ORDER BY installed_rank')==(('0',),('1',),('2',),('3',),('4',),('5',),('6',),('7',)))
    check('new private files jobs rows identities and audits empty',all(sql('SELECT COUNT(*) FROM '+table)[0][0]==0 for table in ['ful_private_file','ful_file_job','ful_file_job_row','ful_import_identity','ful_operation_audit']))
    check('global admission gate initialized only',sql('SELECT tenant_id FROM ful_job_gate')==((0,),))
    check('eight file warehouse audit permissions added',sql('SELECT COUNT(*) FROM system_menu WHERE id BETWEEN 50019 AND 50026 AND deleted=0')[0][0]==8)
    E['result']='passed'
except Exception as error:E['result']='failed';E['error']=str(error);raise
finally:
    (ROOT/'../学习资料/10-验收证据/M6-upgrade.json').write_text(json.dumps(E,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
    print('M6 upgrade',E.get('result'),len(E['checks']),'checks')
