import os
"""M4.1 delivery integrity: actual evidence, immutable migrations/licenses,
selected JUnit reports, source inventory and local documentation links.
Does not substitute for HTTP/MySQL acceptance or a performance test.
"""
import hashlib,json,re,shutil,xml.etree.ElementTree as ET
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import unquote
from m1_acceptance import ROOT,sql
from m3_acceptance import M3Client

E={'run_at':datetime.now(timezone.utc).isoformat(),'checks':[]}
def check(name,ok,detail=None):
    E['checks'].append({'name':name,'passed':bool(ok),'detail':detail})
    if not ok:raise AssertionError(name+': '+str(detail))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def load(name):return json.loads((ROOT/'../学习资料/10-验收证据'/name).read_text(encoding='utf-8'))

try:
    build=ROOT/'.local/m4-expiry-build.log';log=build.read_text(encoding='utf-8',errors='replace')
    modules=re.findall(r'^\[INFO\] (.+?) \.{2,} SUCCESS',log,re.M)
    check('backend 22 module build success','BUILD SUCCESS' in log and len(modules)==22,modules)
    suites=[];selected=['OrderStatusCalculatorTest','AllocationPlannerTest','DatabaseCommandRetryTest','LogisticsSignatureTest','FulExpiryScannerTest']
    junit=ROOT/'../学习资料/10-验收证据/M4.1-junit';junit.mkdir(exist_ok=True)
    for name in selected:
        found=list((ROOT/'backend').glob('*/target/surefire-reports/TEST-*.'+name+'.xml'))
        check('one actual selected JUnit report '+name,len(found)==1)
        path=found[0];suite=ET.parse(path).getroot()
        data={k:int(suite.get(k,'0')) for k in ['tests','failures','errors','skipped']};data['name']=suite.get('name');suites.append(data)
        check('selected JUnit passed '+name,data['failures']==data['errors']==data['skipped']==0 and data['tests']>0,data)
        shutil.copyfile(path,junit/path.name)
    check('37 selected actual unit tests',sum(s['tests'] for s in suites)==37)
    shutil.copyfile(build,ROOT/'../学习资料/10-验收证据/M4.1-build.log')
    (ROOT/'../学习资料/10-验收证据/M4.1-build.json').write_text(json.dumps({'run_at':E['run_at'],'status':'passed','modules':modules,'suites':suites,'tests':37,'log_sha256':sha(build)},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for name,expected,key in [('M4.1-expiry-acceptance.json',42,'result'),('M4.1-clean-binding.json',68,'result'),('M4.1-main-activation.json',285,'result'),('M4.1-M3-regression.json',97,'result')]:
        data=load(name);check('executed evidence passed '+name,data.get(key)=='passed' and len(data['checks'])==expected and all(x['passed'] for x in data['checks']))
    check('full dependency restart actual snapshots match',load('M4.1-restart.json')['status']=='passed' and load('M4.1-restart.json')['before']==load('M4.1-restart.json')['after'])
    check('isolated processes stopped',load('M4.1-expiry-acceptance.json')['all_owned_processes_stopped'])
    check('natural clock fixture was not injected',load('M4.1-expiry-acceptance.json')['natural_expiry']['no_deadline_injection'])
    previous={x['path']:x['sha256'] for x in load('M3-changes.json')['files']}
    for version in [1,2,3]:
        path=next((ROOT/'backend/yudao-module-fulfillment/src/main/resources/db/fulfillment').glob('V'+str(version)+'__*.sql'))
        check('executed V'+str(version)+' remains unchanged',sha(path)==previous[os.path.relpath(path,ROOT).replace(chr(92),"/")])
    for source in json.loads((ROOT/'docs/baseline.lock.json').read_text(encoding='utf-8'))['sources']:
        check('original MIT license '+source['directory'],sha(ROOT/source['directory']/'LICENSE')==source['license_sha256'])
    for name,digest in previous.items():
        if name.startswith('frontend/'):
            check('frontend unchanged '+name,sha(ROOT/name)==digest)
    docs=['README.md','../学习资料/09-项目规范与进度/PROJECT_STATUS.md','../学习资料/09-项目规范与进度/AI_IMPLEMENTATION_SPEC.md','../学习资料/00-项目总学习手册.md',
          '../学习资料/05-设计决策与复盘/ADR-013-M4.1-到期任务与系统命令.md','../学习资料/03-阶段原理讲解/M4.1-自动到期与重复任务.md','../学习资料/10-验收证据/M4.1-验收报告.md']
    for name in docs:
        path=ROOT/name;body=path.read_text(encoding='utf-8')
        check('document encoding/fences '+name,'\ufffd' not in body and not body.startswith('\ufeff') and len(re.findall(r'^```',body,re.M))%2==0)
        for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)',body):
            target=unquote(target.strip('<>').split('#')[0])
            if not target or re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:',target):continue
            check('local link '+name+' -> '+target,(path.parent/target).exists())
    root='backend/yudao-module-fulfillment/'
    java=root+'src/main/java/cn/iocoder/yudao/module/fulfillment/'
    changed=docs+[root+'pom.xml',java+'service/FulAllocationService.java',java+'service/FulCommandService.java',java+'service/FulExpiryService.java',
        java+'dal/mysql/FulReservationMapper.java',java+'framework/ExpiryProperties.java',java+'framework/ExpirySchedulingConfiguration.java',
        java+'framework/FulExpiryScanner.java',java+'framework/ExpiryFaultTestConfiguration.java',
        root+'src/test/java/cn/iocoder/yudao/module/fulfillment/framework/FulExpiryScannerTest.java',
        'backend/yudao-server/src/main/resources/application-fulfillment.yaml','tests/m4_expiry_acceptance.py','tests/m4_expiry_main.py','tests/m4_expiry_qa.py','tests/m3_acceptance.py','tests/m3_instances.ps1']
    inventory=[]
    for name in changed:
        path=ROOT/name;check('changed source exists '+name,path.is_file())
        inventory.append({'path':name,'sha256':sha(path),'previous_M3_sha256':previous.get(name)})
    (ROOT/'../学习资料/10-验收证据/M4.1-changes.json').write_text(json.dumps({'run_at':E['run_at'],'note':'Explicit M4.1 file inventory, not a Git diff; root repository has no commits. Immutable V1-V3 and upstream pins verified separately.','files':inventory},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    check('running and test jars match verified build',sha(ROOT/'.local/backend-run.jar')==sha(ROOT/'.local/m4-expiry-run.jar')==sha(ROOT/'backend/yudao-server/target/yudao-server.jar'))
    runtime=load('M4.1-runtime.json')
    check('final actual listener inventory',set(x['LocalPort'] for x in runtime['listeners'])=={3306,15173,33306,36379,48080})
    check('final test listener inventory empty',runtime['test_ports_free'] and not runtime['test_listeners'])
    check('final main authentication works',bool(M3Client().login().s.headers.get('Authorization')))
    check('final main inventory facts after M3 regression',not sql('SELECT s.id FROM erp_stock s WHERE s.`count`<s.ful_reserved_count OR s.ful_reserved_count<0 OR s.ful_reserved_count<>(SELECT COALESCE(SUM(r.held_qty),0) FROM ful_reservation r WHERE r.tenant_id=s.tenant_id AND r.product_id=s.product_id AND r.warehouse_id=s.warehouse_id) OR s.ful_reserved_count<>(SELECT COALESCE(SUM(l.held_delta),0) FROM ful_stock_ledger l WHERE l.tenant_id=s.tenant_id AND l.product_id=s.product_id AND l.warehouse_id=s.warehouse_id) OR s.`count`<>(SELECT COALESCE(SUM(l.`count`),0) FROM erp_stock_record l WHERE l.tenant_id=s.tenant_id AND l.product_id=s.product_id AND l.warehouse_id=s.warehouse_id)'))
    check('final main order aggregates after M3 regression',not sql('SELECT i.id FROM ful_order_item i WHERE i.reserved_qty<>(SELECT COALESCE(SUM(r.held_qty),0) FROM ful_reservation r WHERE r.tenant_id=i.tenant_id AND r.order_item_id=i.id) OR i.shipped_qty<>(SELECT COALESCE(SUM(s.quantity),0) FROM ful_shipment_item s WHERE s.tenant_id=i.tenant_id AND s.order_item_id=i.id) OR i.cancelled_qty<>(SELECT COALESCE(SUM(c.quantity),0) FROM ful_cancellation c WHERE c.tenant_id=i.tenant_id AND c.order_item_id=i.id)'))
    E['status']='passed'
except Exception as error:E['status']='failed';E['error']=str(error);raise
finally:
    (ROOT/'../学习资料/10-验收证据/M4.1-final-qa.json').write_text(json.dumps(E,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('M4.1 final QA',E.get('status'),len(E['checks']),'checks')
