"""Final M4.3 delivery checks and archival; no business writes or migrations."""
import hashlib,json,os,py_compile,re,shutil,xml.etree.ElementTree as ET
from datetime import datetime,timezone
from urllib.parse import unquote
from PIL import Image
os.environ['DB_NAME']='fulfillment';os.environ['API_BASE']='http://127.0.0.1:48080'
from m1_acceptance import ROOT,sql
from m3_acceptance import M3Client
OUT=ROOT/'../学习资料/10-验收证据';E={'run_at':datetime.now(timezone.utc).isoformat(),'checks':[]}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(name):return json.loads((OUT/name).read_text(encoding='utf-8-sig'))
def save(name,data):(OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
def check(name,ok,detail=None):
    E['checks'].append({'name':name,'passed':bool(ok),'detail':detail})
    if not ok:raise AssertionError(name+': '+str(detail))
try:
    build=ROOT/'.local/m4-reconcile-final-build.log';log=build.read_text(encoding='utf-8',errors='replace');modules=re.findall(r'^\[INFO\] (.+?) \.{2,} SUCCESS',log,re.M)
    check('final 22 module build success','BUILD SUCCESS' in log and len(modules)==22)
    suites=[];folder=OUT/'M4.3-junit';folder.mkdir(exist_ok=True)
    for name in ['OrderStatusCalculatorTest','AllocationPlannerTest','DatabaseCommandRetryTest','LogisticsSignatureTest','FulExpiryScannerTest','ReconcileEngineTest']:
        found=list((ROOT/'backend').glob('*/target/surefire-reports/TEST-*.'+name+'.xml'));check('one selected JUnit '+name,len(found)==1)
        suite=ET.parse(found[0]).getroot();d={k:int(suite.get(k,'0')) for k in ['tests','failures','errors','skipped']};d['name']=suite.get('name');suites.append(d)
        check('selected tests passed '+name,d['tests']>0 and d['failures']==d['errors']==d['skipped']==0,d);shutil.copyfile(found[0],folder/found[0].name)
    check('44 selected unit tests',sum(s['tests'] for s in suites)==44)
    shutil.copyfile(build,OUT/'M4.3-build.log')
    artifacts={name:sha(ROOT/name) for name in ['backend/yudao-server/target/yudao-server.jar','.local/backend-run.jar','.local/m4-reconcile-run.jar','.local/m4-reconcile-ui.jar']}
    check('main core UI retained artifacts match final build',len(set(artifacts.values()))==1,artifacts)
    save('M4.3-build.json',{'run_at':E['run_at'],'status':'passed','modules':modules,'suites':suites,'tests':44,'artifacts':artifacts,'log_sha256':sha(build)})
    for name,count,key in [('reconcile-acceptance',73,'result'),('clean-binding',68,'result'),('ERP-regression',110,'status'),('upgrade',29,'result'),('constraints',8,'result'),('ui-result',7,'result'),('replay-after-restart',7,'result'),('frontend',4,'status')]:
        d=load('M4.3-'+name+'.json');check('actual passed evidence '+name,d.get(key)=='passed' and len(d['checks'])==count and all(x['passed'] for x in d['checks']))
    core=load('M4.3-reconcile-acceptance.json');check('core owned JVMs stopped',core['all_owned_processes_stopped'])
    check('ten isolated corruption probes recorded',len(core['injections'])==10)
    check('no foreign main schema in corruption evidence',core['database'].startswith('fulfillment_m4_reconcile_'))
    restart=load('M4.3-restart.json');check('full restart including report facts equal',restart['status']=='passed' and restart['before']==restart['after'] and 'ful_reconcile_review_facts' in restart['before'])
    for name in ['snapshot','fault']:
        path=ROOT/('.local/m4-reconcile-'+name+'-out.log');body=path.read_text(encoding='utf-8',errors='replace')
        check('real inner RR and outer RC '+name,'M4_RECONCILE_ISOLATION REPEATABLE-READ' in body and 'M4_RECONCILE_OUTER_ISOLATION READ-COMMITTED' in body)
    archive=['m4-reconcile-final-build.log','m4-reconcile-acceptance.log','m4-reconcile-restart-run.log','m4-reconcile-restart.log','m4-reconcile-main-migrate.log','m4-reconcile-main-validate.log','m4-reconcile-frontend-eslint.log','m4-reconcile-frontend-stylelint.log','m4-reconcile-frontend-prettier.log','m4-reconcile-frontend-build.log','m4-reconcile-ui-m1_acceptance.py.log','m4-reconcile-ui-m0_smoke.py.log']
    for name in archive:
        p=ROOT/'.local'/name;check('log retained '+name,p.is_file());shutil.copyfile(p,OUT/('M4.3-'+name))
    for entry in core['commands']:
        check('executed setup command succeeded',entry['exit_code']==0);p=ROOT/entry['log'];shutil.copyfile(p,OUT/('M4.3-'+p.name))
    detector=ROOT/'.local/m4-reconcile-detector.json';check('mechanical frontend detector empty',json.loads(detector.read_text(encoding='utf-8-sig'))==[]);shutil.copyfile(detector,OUT/'M4.3-detector.json')
    previous={x['path']:x['sha256'] for x in load('M3-changes.json')['files']};previous.update({x['path']:x['sha256'] for x in load('M4.2-changes.json')['files'] if '/db/fulfillment/' in x['path']})
    migrations=ROOT/'backend/yudao-module-fulfillment/src/main/resources/db/fulfillment'
    for version in [1,2,3,4]:
        p=next(migrations.glob('V'+str(version)+'__*.sql'));check('immutable V'+str(version),sha(p)==previous[os.path.relpath(p,ROOT).replace(chr(92),"/")])
    dbname=core['database'];check('safe isolated schema',bool(re.fullmatch(r'fulfillment_m4_reconcile_\d{8}_\d{6}',dbname)))
    history=sql('SELECT version,checksum,success FROM ful_flyway_schema_history ORDER BY installed_rank')
    check('main and isolated V0-V5 history matches',history==sql('SELECT version,checksum,success FROM `'+dbname+'`.ful_flyway_schema_history ORDER BY installed_rank') and tuple(x[0] for x in history)==('0','1','2','3','4','5') and all(x[2] for x in history),history)
    for s in json.loads((ROOT/'docs/baseline.lock.json').read_text(encoding='utf-8'))['sources']:check('original MIT '+s['directory'],sha(ROOT/s['directory']/'LICENSE')==s['license_sha256'])
    # ERP Java and initialization source/manifest are unchanged by M4.3.
    prior=load('M4.2-changes.json')
    for entry in prior['files']:
        if entry['path'].startswith('backend/yudao-module-erp/'):check('existing ERP Java preserved '+entry['path'],sha(ROOT/entry['path'])==entry['sha256'])
    docs=['README.md','../学习资料/09-项目规范与进度/PROJECT_STATUS.md','../学习资料/09-项目规范与进度/AI_IMPLEMENTATION_SPEC.md','../学习资料/00-项目总学习手册.md','../学习资料/05-设计决策与复盘/ADR-015-M4.3-快照核对与差异追溯.md','../学习资料/03-阶段原理讲解/M4.3-一致性快照与差异核对.md','../学习资料/10-验收证据/M4.3-验收报告.md','../学习资料/01-系统学习教程/README.md','../学习资料/02-面试问答/README.md']
    for name in docs:
        p=ROOT/name;body=p.read_text(encoding='utf-8');check('UTF8 and code fences '+name,'\ufffd' not in body and not body.startswith('\ufeff') and len(re.findall(r'^```',body,re.M))%2==0)
        for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)',body):
            target=unquote(target.strip('<>').split('#')[0])
            if not target or re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:',target):continue
            check('local link '+name+' -> '+target,(p.parent/target).exists())
    ful='backend/yudao-module-fulfillment/src/main/java/cn/iocoder/yudao/module/fulfillment/'
    changed=docs+[ful+x for x in ['controller/admin/ReconcileContracts.java','controller/admin/FulReconcileController.java','domain/ReconcileEngine.java','service/ReconcileSnapshotObserver.java','service/FulReconcileService.java','service/FulReconcileSnapshotReader.java','service/ReconcileAdmission.java','framework/ReconcileTestConfiguration.java','enums/FulfillmentErrors.java']]+['backend/yudao-module-fulfillment/src/main/resources/db/fulfillment/V5__reconciliation.sql','backend/yudao-module-fulfillment/src/test/java/cn/iocoder/yudao/module/fulfillment/domain/ReconcileEngineTest.java','frontend/src/api/erp/reconciliation/index.ts','frontend/src/views/erp/reconciliation/index.vue','tests/m0_restart.py']+[os.path.relpath(p,ROOT).replace(chr(92),"/") for p in sorted((ROOT/'tests').glob('m4_reconcile_*')) if p.suffix in ['.py','.ps1']]
    check('explicit inventory has no duplicates',len(changed)==len(set(changed)))
    files=[]
    for name in changed:
        p=ROOT/name;check('source exists '+name,p.is_file());files.append({'path':name,'sha256':sha(p)})
        if p.suffix=='.py':py_compile.compile(str(p),doraise=True);check('Python compiles '+name,True)
    save('M4.3-changes.json',{'run_at':E['run_at'],'note':'Explicit stage inventory, not a Git diff. M4.2 learning pack remains a historical snapshot; only its entry notices were updated.','count':len(files),'files':files})
    for name,dimensions in [('desktop',(1280,900)),('mobile',(390,844))]:
        with Image.open(OUT/('M4.3-ui-'+name+'.jpg')) as pic:check('real browser JPEG '+name,pic.format=='JPEG' and pic.size==dimensions,{'format':pic.format,'dimensions':pic.size})
    layout=load('M4.3-ui-layout.json');check('two bounded UI rounds',layout['result']=='passed' and layout['rounds']==2)
    for name in ['desktop','mobile']:
        d=layout[name];check('no whole-page overflow '+name,d['width']==d['bodyWidth'] and d['drawerWidth']<=d['width'] and d['reviewWidth']<d['drawerWidth']);check('drawer tokens apply '+name,d['primary']=='#2d6fb3' and d['placeholder']=='#606266')
    runtime=load('M4.3-runtime.json');check('actual main and system listeners',set(x['LocalPort'] for x in runtime['listeners'])=={3306,15173,33306,36379,48080});check('isolated listeners stopped',runtime['test_ports_free'] and not runtime['test_listeners'])
    c=M3Client().login();saved=load('M4.3-replay-after-restart.json')['report'];check('current main saved report unchanged and clean',c.api('GET','/fulfillment/reconcile/get',params={'id':saved['id']})==saved and saved['differenceCount']==0)
    E['source_count']=len(files);E['status']='passed'
except Exception as error:E['status']='failed';E['error']=str(error);raise
finally:
    save('M4.3-final-qa.json',E);print('M4.3 final QA',E.get('status'),len(E['checks']),'checks; files',E.get('source_count'))
