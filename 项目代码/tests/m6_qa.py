"""Final M6 delivery audit. Uses current evidence; never rewrites history."""
import hashlib,json,os,py_compile,re,shutil,xml.etree.ElementTree as ET
from datetime import datetime,timezone
from urllib.parse import unquote
from PIL import Image
os.environ['DB_NAME']='fulfillment'
from m1_acceptance import ROOT,sql
OUT=ROOT/'../学习资料/10-验收证据';E={'run_at':datetime.now(timezone.utc).isoformat(),'checks':[]}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(n):return json.loads((OUT/n).read_text(encoding='utf-8-sig'))
def save(n,d):(OUT/n).write_text(json.dumps(d,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
def check(n,ok,d=None):
    E['checks'].append({'name':n,'passed':bool(ok),'detail':d})
    if not ok:raise AssertionError(n+': '+str(d))
save('M6-final-qa.json',dict(E,status='running'))
try:
    build=ROOT/'.local/m6-final-build.log';body=build.read_text(encoding='utf-8',errors='replace');modules=re.findall(r'^\[INFO\] (.+?) \.{2,} SUCCESS',body,re.M)
    check('22 module build succeeds','BUILD SUCCESS' in body and len(modules)==22)
    junit=OUT/'M6-junit';junit.mkdir(exist_ok=True);suites=[]
    for name in ['OrderStatusCalculatorTest','AllocationPlannerTest','DatabaseCommandRetryTest','LogisticsSignatureTest','FulExpiryScannerTest','ReconcileEngineTest','FulfillmentEventTest','ImportCsvTest']:
        paths=list((ROOT/'backend').glob('*/target/surefire-reports/TEST-*.'+name+'.xml'));check('one selected suite '+name,len(paths)==1)
        s=ET.parse(paths[0]).getroot();d={k:int(s.get(k,'0')) for k in ['tests','failures','errors','skipped']};d['name']=s.get('name');suites.append(d)
        check('suite passed '+name,d['tests']>0 and d['failures']==d['errors']==d['skipped']==0,d);shutil.copyfile(paths[0],junit/paths[0].name)
    check('60 selected actual JUnit tests',sum(s['tests'] for s in suites)==60)
    core=load('M6-acceptance.json');artifacts={n:sha(ROOT/n) for n in ['backend/yudao-server/target/yudao-server.jar','.local/m6-test.jar','.local/backend-run.jar']}
    check('foundation core main exact final artifact',len(set(artifacts.values()))==1 and next(iter(artifacts.values()))==core['artifact_sha256']==load('M6.1-foundation.json')['artifact_sha256'],artifacts)
    save('M6-build.json',{'status':'passed','modules':modules,'tests':60,'suites':suites,'artifacts':artifacts})
    for name,key in [('acceptance','result'),('supplement','result'),('constraints','result'),('M1-regression','result'),('ERP-regression','status'),('upgrade','result'),('main-demo','result'),('browser-SQL','result'),('replay-after-restart','result'),('frontend','status')]:
        d=load('M6-'+name+'.json');check('passed evidence '+name,d.get(key)=='passed' and all(x['passed'] for x in d['checks']),len(d['checks']))
    check('core supplement JVMs stopped',core['all_owned_processes_stopped'] and load('M6-supplement.json')['all_owned_processes_stopped'])
    r=load('M6-restart.json');check('full dependency snapshots exact',r['status']=='passed' and r['before']==r['after'])
    prior={}
    for name in ['M3-changes.json','M4.2-changes.json','M4.3-changes.json','M5-changes.json']:
        prior.update({x['path']:x['sha256'] for x in load(name)['files'] if '/db/fulfillment/' in x['path']})
    for v in range(1,7):
        p=next((ROOT/'backend/yudao-module-fulfillment/src/main/resources/db/fulfillment').glob('V'+str(v)+'__*.sql'));check('immutable V'+str(v),sha(p)==prior[os.path.relpath(p,ROOT).replace(chr(92),"/")])
    database=core['database'];check('safe isolated schema',bool(re.fullmatch(r'fulfillment_m6_\d{8}_\d{6}',database)))
    history=sql('SELECT version,checksum,success FROM ful_flyway_schema_history ORDER BY installed_rank')
    check('main isolated V0-V7 checksums equal',history==sql('SELECT version,checksum,success FROM `'+database+'`.ful_flyway_schema_history ORDER BY installed_rank') and tuple(x[0] for x in history)==tuple(str(v) for v in range(8)) and all(x[2] for x in history),history)
    for source in json.loads((ROOT/'docs/baseline.lock.json').read_text(encoding='utf-8'))['sources']:check('original MIT '+source['directory'],sha(ROOT/source['directory']/'LICENSE')==source['license_sha256'])
    for e in load('M4.2-changes.json')['files']:
        if e['path'].startswith('backend/yudao-module-erp/'):check('preserved ERP '+e['path'],sha(ROOT/e['path'])==e['sha256'])
    docs=['README.md','../学习资料/09-项目规范与进度/PROJECT_STATUS.md','../学习资料/09-项目规范与进度/AI_IMPLEMENTATION_SPEC.md','../学习资料/00-项目总学习手册.md','../学习资料/05-设计决策与复盘/ADR-017-M6-持久化文件任务与数据授权.md','../学习资料/03-阶段原理讲解/M6-可恢复文件任务与仓库授权.md','../学习资料/10-验收证据/M6-验收报告.md','../学习资料/01-系统学习教程/README.md','../学习资料/02-面试问答/README.md']
    ful='backend/yudao-module-fulfillment/src/main/java/cn/iocoder/yudao/module/fulfillment/'
    names=['controller/admin/FileJobContracts.java','controller/admin/FulFileJobController.java','controller/admin/FulWarehouseController.java','framework/FileJobProperties.java','framework/FileJobConfiguration.java','framework/FileJobFaultTestConfiguration.java','domain/ImportCsv.java','service/JobValues.java','service/FulOperationAudit.java','service/FulWarehouseAccess.java','service/FulPrivateFiles.java','service/FulJobAuthorization.java','service/FulJobStore.java','service/FulDraftImport.java','service/FulJobExport.java','service/FulJobProcessor.java','service/FulJobFault.java','service/FulAllocationService.java','service/FulExecutionService.java','service/FulWorkbenchService.java','service/FulReturnService.java','controller/admin/FulAllocationController.java','enums/FulfillmentErrors.java']
    changed=docs+[ful+n for n in names]+['backend/yudao-server/src/main/resources/application-fulfillment.yaml','backend/yudao-module-fulfillment/src/main/resources/db/fulfillment/V7__file_jobs_and_warehouse_scope.sql','backend/yudao-module-fulfillment/src/test/java/cn/iocoder/yudao/module/fulfillment/domain/ImportCsvTest.java','frontend/src/api/erp/fulfillment/jobs.ts','frontend/src/views/erp/fulfillment-jobs/index.vue','frontend/src/views/erp/fulfillment-warehouse/index.vue','tests/m0_restart.py','scripts/Start-Local.ps1']
    changed += [os.path.relpath(p,ROOT).replace(chr(92),"/") for p in sorted((ROOT/'tests').glob('m6_*')) if p.suffix in ['.py','.ps1']]
    check('unique explicit inventory',len(changed)==len(set(changed)));files=[]
    for name in changed:
        p=ROOT/name;check('source exists '+name,p.is_file());files.append({'path':name,'sha256':sha(p)})
        if p.suffix=='.py':py_compile.compile(str(p),doraise=True)
    save('M6-changes.json',{'note':'Explicit M6 source inventory, not Git diff. Historical M4.2 packs remain historical.','count':len(files),'files':files})
    for name in docs:
        p=ROOT/name;text=p.read_text(encoding='utf-8');check('UTF8 fences '+name,'\ufffd' not in text and not text.startswith('\ufeff') and len(re.findall(r'^```',text,re.M))%2==0)
        for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)',text):
            target=unquote(target.strip('<>').split('#')[0])
            if not target or re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:',target):continue
            check('link '+name+' -> '+target,(p.parent/target).exists())
    for p in (ROOT/'.local').glob('m6-*.log'):shutil.copyfile(p,OUT/('M6-'+p.name))
    layout=load('M6-ui-layout.json');check('bounded desktop mobile rounds',layout['result']=='passed' and 1<=layout['rounds']<=2)
    for page in ['jobs','warehouse']:
        for viewport,size in [('desktop',(1280,900)),('mobile',(390,844))]:
            with Image.open(OUT/('M6-ui-'+page+'-'+viewport+'.jpg')) as image:check('actual screenshot '+page+viewport,image.format=='JPEG' and image.size==size)
            d=layout[page][viewport];check('no page overflow '+page+viewport,d['pageWidth']==d['viewportWidth'])
    check('UI detector no findings',load('M6-ui-detect.json')==[])
    runtime=load('M6-runtime.json');check('main and system listeners',set(x['LocalPort'] for x in runtime['listeners'])=={3306,15173,33306,36379,48080,35672,35673,35674,35675});check('test ports free',runtime['test_ports_free'])
    E.update(source_count=len(files),status='passed')
except Exception as error:E['status']='failed';E['error']=str(error);raise
finally:save('M6-final-qa.json',E);print('M6 QA',E.get('status'),len(E['checks']),'checks',flush=True)
