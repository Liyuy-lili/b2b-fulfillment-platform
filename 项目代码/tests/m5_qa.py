"""Bounded final delivery audit and evidence archive. No business mutations."""
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
try:
    build=ROOT/'.local/m5-build.log';body=build.read_text(encoding='utf-8',errors='replace');modules=re.findall(r'^\[INFO\] (.+?) \.{2,} SUCCESS',body,re.M)
    check('22 module build succeeds','BUILD SUCCESS' in body and len(modules)==22)
    junit=OUT/'M5-junit';junit.mkdir(exist_ok=True);suites=[]
    for name in ['OrderStatusCalculatorTest','AllocationPlannerTest','DatabaseCommandRetryTest','LogisticsSignatureTest','FulExpiryScannerTest','ReconcileEngineTest','FulfillmentEventTest']:
        files=list((ROOT/'backend').glob('*/target/surefire-reports/TEST-*.'+name+'.xml'));check('one selected suite '+name,len(files)==1)
        s=ET.parse(files[0]).getroot();d={k:int(s.get(k,'0')) for k in ['tests','failures','errors','skipped']};d['name']=s.get('name');suites.append(d)
        check('suite passed '+name,d['tests']>0 and d['failures']==d['errors']==d['skipped']==0,d);shutil.copyfile(files[0],junit/files[0].name)
    check('51 selected actual JUnit tests',sum(s['tests'] for s in suites)==51)
    core=load('M5-acceptance.json');artifacts={n:sha(ROOT/n) for n in ['backend/yudao-server/target/yudao-server.jar','.local/m5-test.jar','.local/backend-run.jar']}
    check('main and core exact final artifact',len(set(artifacts.values()))==1 and next(iter(artifacts.values()))==core['artifact_sha256'],artifacts)
    save('M5-build.json',{'status':'passed','modules':modules,'tests':51,'suites':suites,'artifacts':artifacts})
    for name,key in [('acceptance','result'),('supplement','result'),('constraints','result'),('M1-regression','result'),('ERP-regression','status'),('upgrade','result'),('main-demo','result'),('browser-SQL','result'),('replay-after-restart','result'),('frontend','status')]:
        d=load('M5-'+name+'.json');check('passed evidence '+name,d.get(key)=='passed' and all(x['passed'] for x in d['checks']),len(d['checks']))
    check('core and supplement JVMs stopped',core['all_owned_processes_stopped'] and load('M5-supplement.json')['all_owned_processes_stopped'])
    restart=load('M5-restart.json');check('full dependency snapshots match',restart['status']=='passed' and restart['before']==restart['after'])
    prior={x['path']:x['sha256'] for x in load('M3-changes.json')['files']}
    for name in ['M4.2-changes.json','M4.3-changes.json']:prior.update({x['path']:x['sha256'] for x in load(name)['files'] if '/db/fulfillment/' in x['path']})
    for v in range(1,6):
        p=next((ROOT/'backend/yudao-module-fulfillment/src/main/resources/db/fulfillment').glob('V'+str(v)+'__*.sql'));check('immutable V'+str(v),sha(p)==prior[os.path.relpath(p,ROOT).replace(chr(92),"/")])
    database=core['database'];check('safe independent schema',bool(re.fullmatch(r'fulfillment_m5_\d{8}_\d{6}',database)))
    history=sql('SELECT version,checksum,success FROM ful_flyway_schema_history ORDER BY installed_rank')
    check('main independent V0-V6 checksums equal',history==sql('SELECT version,checksum,success FROM `'+database+'`.ful_flyway_schema_history ORDER BY installed_rank') and tuple(x[0] for x in history)==tuple(str(v) for v in range(7)) and all(x[2] for x in history),history)
    for source in json.loads((ROOT/'docs/baseline.lock.json').read_text(encoding='utf-8'))['sources']:check('original MIT '+source['directory'],sha(ROOT/source['directory']/'LICENSE')==source['license_sha256'])
    for e in load('M4.2-changes.json')['files']:
        if e['path'].startswith('backend/yudao-module-erp/'):check('preserved ERP '+e['path'],sha(ROOT/e['path'])==e['sha256'])
    docs=['README.md','AGENTS.md','../学习资料/09-项目规范与进度/PROJECT_STATUS.md','../学习资料/09-项目规范与进度/AI_IMPLEMENTATION_SPEC.md','../学习资料/00-项目总学习手册.md','../学习资料/05-设计决策与复盘/ADR-016-M5-可靠事件与消息恢复.md','../学习资料/03-阶段原理讲解/M5-可靠消息与故障恢复.md','../学习资料/10-验收证据/M5-验收报告.md','../学习资料/01-系统学习教程/README.md','../学习资料/02-面试问答/README.md']
    for name in docs:
        p=ROOT/name;text=p.read_text(encoding='utf-8');check('UTF8 fences '+name,'\ufffd' not in text and not text.startswith('\ufeff') and len(re.findall(r'^```',text,re.M))%2==0)
        for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)',text):
            target=unquote(target.strip('<>').split('#')[0])
            if not target or re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:',target):continue
            check('link '+name+' -> '+target,(p.parent/target).exists())
    ful='backend/yudao-module-fulfillment/src/main/java/cn/iocoder/yudao/module/fulfillment/'
    names=['domain/FulfillmentEvent.java','service/FulMessageSnapshots.java','service/FulMessageFault.java','service/FulOutboxService.java','framework/MessageProperties.java','service/FulMessageStore.java','service/FulMessageConsumerService.java','service/FulRabbitTransport.java','service/FulMessageWorker.java','framework/MessagingConfiguration.java','framework/MessageFaultTestConfiguration.java','controller/admin/MessageContracts.java','service/FulMessageAdminService.java','controller/admin/FulMessageController.java','enums/FulfillmentErrors.java','service/FulOrderService.java','service/FulAllocationService.java','service/FulExecutionService.java','service/FulReturnService.java','service/FulExpiryService.java']
    changed=docs+[ful+n for n in names]+['backend/yudao-module-fulfillment/pom.xml','backend/yudao-server/src/main/resources/application-fulfillment.yaml','backend/yudao-module-fulfillment/src/main/resources/db/fulfillment/V6__reliable_messages.sql','backend/yudao-module-fulfillment/src/test/java/cn/iocoder/yudao/module/fulfillment/domain/FulfillmentEventTest.java','frontend/src/api/erp/fulfillment/messages.ts','frontend/src/views/erp/fulfillment/FulfillmentMessages.vue','frontend/src/views/erp/fulfillment/FulfillmentWorkbench.vue','tests/m0_restart.py','tests/requirements.txt']
    changed += [os.path.relpath(p,ROOT).replace(chr(92),"/") for p in sorted((ROOT/'tests').glob('m5_*')) if p.suffix in ['.py','.ps1']]
    changed += ['scripts/'+n for n in ['Bootstrap-Messaging.ps1','Messaging-Environment.ps1','Run-Messaging.ps1','Start-Messaging.ps1','Stop-Messaging.ps1','Start-Local.ps1','Stop-Local.ps1']]
    check('unique explicit source inventory',len(changed)==len(set(changed)))
    files=[]
    for name in changed:
        p=ROOT/name;check('source exists '+name,p.is_file());files.append({'path':name,'sha256':sha(p)})
        if p.suffix=='.py':py_compile.compile(str(p),doraise=True)
    save('M5-changes.json',{'note':'Explicit M5 source inventory, not Git diff. Upstream pins/MIT unchanged. Historical learning packs retained.','count':len(files),'files':files})
    for p in (ROOT/'.local').glob('m5-*.log'):shutil.copyfile(p,OUT/('M5-'+p.name))
    for name,size in [('desktop',(1280,900)),('mobile',(390,844))]:
        with Image.open(OUT/('M5-ui-'+name+'.jpg')) as image:check('browser JPEG '+name,image.format=='JPEG' and image.size==size)
    layout=load('M5-ui-layout.json');check('bounded desktop/mobile layout verified',layout['result']=='passed' and 1<=layout['rounds']<=2)
    for name in ['desktop','mobile']:
        d=layout[name];check('no page overflow '+name,d['pageWidth']==d['viewportWidth'] and d['messageWidth']<=d['drawerWidth']<=d['viewportWidth'])
    check('UI detector no findings',load('M5-ui-detect.json')==[])
    runtime=load('M5-runtime.json');check('actual main and system listeners',set(x['LocalPort'] for x in runtime['listeners'])=={3306,15173,33306,36379,48080,35672,35673,35674,35675});check('independent ports free',runtime['test_ports_free'])
    E['source_count']=len(files);E['status']='passed'
except Exception as error:E['status']='failed';E['error']=str(error);raise
finally:save('M5-final-qa.json',E);print('M5 final QA',E.get('status'),len(E['checks']),'checks')
