"""One-time V7->V8 main index migration, exact facts and immutable history."""
import hashlib,json,os
from datetime import datetime,timezone
import m7_support as h
from m0_restart import snapshot
E={'run_at':datetime.now(timezone.utc).isoformat(),'checks':[],'commands':[]};q=lambda s,a=():h.sql('fulfillment',s,a)
def check(name,ok,detail=None):
    E['checks'].append(dict(name=name,passed=bool(ok),detail=detail));print(name,ok,flush=True);assert ok,name
def all_facts():
    tables=q("SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND (LEFT(TABLE_NAME,4)='erp_' OR LEFT(TABLE_NAME,4)='ful_') AND TABLE_NAME<>'ful_flyway_schema_history' ORDER BY TABLE_NAME")
    return {t[0]:q('SELECT * FROM `'+t[0]+'` ORDER BY '+('tenant_id' if t[0]=='ful_job_gate' else 'id')) for t in tables}
try:
    os.environ['DB_NAME']='fulfillment';check('all final regression gates passed',all(h.load('M7.2-'+c+'-run.json')['result']=='passed' for c in ['core','expiry','returns','reconcile','message','filefoundation','file']))
    check('both performance experiments passed',all(h.load('M7.3-'+c+'.json')['result']=='passed' for c in ['query','stock']))
    check('matching selected build',h.sha(h.JAR)==h.load('M7-build.json')['backend_sha256'])
    E['commands'].append(h.shell('scripts/Stop-Local.ps1',label='m7-main-stop'));check('main apps stopped',h.free(48080) and h.free(15173))
    history=q('SELECT * FROM ful_flyway_schema_history ORDER BY installed_rank');check('one time V0-V7 starting history',q('SELECT version FROM ful_flyway_schema_history ORDER BY installed_rank')==tuple((str(n),) for n in range(8)))
    inventories={}
    for name in ['M3-changes.json','M4.2-changes.json','M4.3-changes.json','M5-changes.json','M6-changes.json']:
        inventories.update({x['path']:x['sha256'] for x in h.load(name)['files'] if '/db/fulfillment/' in x['path']})
    for n in range(1,8):
        path=next((h.ROOT/'backend/yudao-module-fulfillment/src/main/resources/db/fulfillment').glob('V'+str(n)+'__*.sql'));check('immutable V'+str(n),h.sha(path)==inventories[path.relative_to(h.ROOT).as_posix()])
    before=all_facts();E['before_snapshot']=snapshot();E['before_fact_sha256']=hashlib.sha256(json.dumps(before,default=str,sort_keys=True).encode()).hexdigest()
    for action in ['migrate','validate']:E['commands'].append(h.shell('scripts/Migrate-Database.ps1','-Action',action,'-Database','fulfillment',label='m7-main-'+action))
    after=all_facts();E['after_fact_sha256']=hashlib.sha256(json.dumps(after,default=str,sort_keys=True).encode()).hexdigest();check('every ERP and fulfillment row preserved',before==after)
    now=snapshot();E['after_snapshot']=now
    for name,value in E['before_snapshot'].items():
        check('snapshot preserved '+name,all(now[name][k]==v for k,v in value.items() if k!='ful_flyway_schema_history') if name=='fulfillment_counts' else now[name]==value)
    check('old history unchanged plus V8',q('SELECT * FROM ful_flyway_schema_history ORDER BY installed_rank')[:-1]==history and q('SELECT version FROM ful_flyway_schema_history ORDER BY installed_rank')==tuple((str(n),) for n in range(9)))
    E['index']=q("SELECT INDEX_NAME,SEQ_IN_INDEX,COLUMN_NAME,IS_VISIBLE FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='ful_order' AND INDEX_NAME='ix_order_tenant_deleted_status_id' ORDER BY SEQ_IN_INDEX")
    check('V8 four-column index visible',[(r[2],r[3]) for r in E['index']]==[(x,'YES') for x in ['tenant_id','deleted','status','id']])
    E['commands'].append(h.shell('scripts/Start-Local.ps1',label='m7-main-start'));h.wait(lambda:h.Client(48080).login(),150);check('main runs final artifact',h.sha(h.ROOT/'.local/backend-run.jar')==h.sha(h.JAR));E['result']='passed'
except Exception as error:E.update(result='failed',error=str(error));raise
finally:h.save('M7-main-upgrade.json',E)
