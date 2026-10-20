"""M4.2 delivery integrity. Read-only business checks; no migration or fixture writes.
Archives actual logs/reports and an explicit source inventory, not a Git diff.
"""
import hashlib,json,os,py_compile,re,shutil,xml.etree.ElementTree as ET
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import unquote
from PIL import Image
os.environ['DB_NAME']='fulfillment'
os.environ['API_BASE']='http://127.0.0.1:48080'
from m1_acceptance import ROOT,sql
from m3_acceptance import M3Client

OUT=ROOT/'../学习资料/10-验收证据'
E={'run_at':datetime.now(timezone.utc).isoformat(),'checks':[]}
def check(name,ok,detail=None):
    E['checks'].append({'name':name,'passed':bool(ok),'detail':detail})
    if not ok:raise AssertionError(name+': '+str(detail))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def load(name):return json.loads((OUT/name).read_text(encoding='utf-8-sig'))
def save(name,value):(OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')

try:
    build=ROOT/'.local/m4-return-build.log';log=build.read_text(encoding='utf-8',errors='replace')
    modules=re.findall(r'^\[INFO\] (.+?) \.{2,} SUCCESS',log,re.M)
    check('backend 22 module build success','BUILD SUCCESS' in log and len(modules)==22,modules)
    suites=[];junit=OUT/'M4.2-junit';junit.mkdir(exist_ok=True)
    for name in ['OrderStatusCalculatorTest','AllocationPlannerTest','DatabaseCommandRetryTest','LogisticsSignatureTest','FulExpiryScannerTest']:
        found=list((ROOT/'backend').glob('*/target/surefire-reports/TEST-*.'+name+'.xml'))
        check('one selected JUnit report '+name,len(found)==1)
        path=found[0];suite=ET.parse(path).getroot()
        data={k:int(suite.get(k,'0')) for k in ['tests','failures','errors','skipped']};data['name']=suite.get('name');suites.append(data)
        check('selected JUnit passed '+name,data['failures']==data['errors']==data['skipped']==0 and data['tests']>0,data)
        shutil.copyfile(path,junit/path.name)
    check('37 actual selected unit tests',sum(s['tests'] for s in suites)==37)
    shutil.copyfile(build,OUT/'M4.2-build.log')
    save('M4.2-build.json',{'run_at':E['run_at'],'status':'passed','modules':modules,'suites':suites,'tests':37,'log_sha256':sha(build)})
    for name,count,key in [('return-acceptance',71,'result'),('clean-binding',68,'result'),('final-api',22,'result'),('ERP-regression',110,'status'),('upgrade',25,'result'),('constraints',10,'result'),('ui-result',21,'result'),('replay-after-restart',12,'result'),('frontend',4,'status')]:
        data=load('M4.2-'+name+'.json')
        check('executed evidence passed '+name,data.get(key)=='passed' and len(data['checks'])==count and all(x['passed'] for x in data['checks']))
    for name in ['return-acceptance','final-api']:
        check('owned test processes stopped '+name,load('M4.2-'+name+'.json')['all_owned_processes_stopped'])
    restart=load('M4.2-restart.json')
    check('full dependency restart exact snapshots',restart['status']=='passed' and restart['before']==restart['after'])
    for suffix in ['final-read-out','erp-regression','restart-run','frontend-eslint','frontend-stylelint','frontend-prettier','frontend-build']:
        path=ROOT/('.local/m4-return-'+suffix+'.log')
        # Successful linters may emit zero bytes; exit codes live in frontend.json.
        check('actual log retained '+suffix,path.is_file())
        shutil.copyfile(path,OUT/('M4.2-'+suffix+'.log'))
    detector=ROOT/'.local/m4-return-detector.json'
    check('actual frontend detector empty',json.loads(detector.read_text(encoding='utf-8-sig'))==[])
    shutil.copyfile(detector,OUT/'M4.2-detector.json')
    previous={x['path']:x['sha256'] for x in load('M3-changes.json')['files']}
    migrations=ROOT/'backend/yudao-module-fulfillment/src/main/resources/db/fulfillment'
    for version in [1,2,3]:
        path=next(migrations.glob('V'+str(version)+'__*.sql'))
        check('immutable executed migration V'+str(version),sha(path)==previous[os.path.relpath(path,ROOT).replace(chr(92),"/")])
    core_db=load('M4.2-return-acceptance.json')['database']
    check('isolated database name safe',bool(re.fullmatch(r'fulfillment_m4_return_\d{8}_\d{6}',core_db)))
    history=sql('SELECT version,checksum,success FROM ful_flyway_schema_history ORDER BY installed_rank')
    other=sql('SELECT version,checksum,success FROM `'+core_db+'`.ful_flyway_schema_history ORDER BY installed_rank')
    check('main and isolated successful migration checksums agree',history==other and tuple(x[0] for x in history)==('0','1','2','3','4') and all(x[2] for x in history),history)
    for source in json.loads((ROOT/'docs/baseline.lock.json').read_text(encoding='utf-8'))['sources']:
        check('retained MIT '+source['directory'],sha(ROOT/source['directory']/'LICENSE')==source['license_sha256'])
    older={x['path']:x['sha256'] for x in load('M4.1-changes.json')['files']}
    docs=['README.md','../学习资料/09-项目规范与进度/PROJECT_STATUS.md','../学习资料/09-项目规范与进度/AI_IMPLEMENTATION_SPEC.md','../学习资料/00-项目总学习手册.md',
          '../学习资料/05-设计决策与复盘/ADR-014-M4.2-退货与ERP入库.md','../学习资料/03-阶段原理讲解/M4.2-退货额度与ERP入库.md','../学习资料/10-验收证据/M4.2-验收报告.md']
    ful='backend/yudao-module-fulfillment/src/main/java/cn/iocoder/yudao/module/fulfillment/'
    erp='backend/yudao-module-erp/src/main/java/cn/iocoder/yudao/module/erp/service/sale/'
    changed=docs+[erp+x for x in ['managed/ErpManagedSaleReturnPort.java','ErpSaleReturnServiceImpl.java','ErpSaleOrderService.java','ErpSaleOrderServiceImpl.java']]+[ful+x for x in ['dal/dataobject/FulReturnDO.java','dal/dataobject/FulReturnItemDO.java','dal/mysql/FulReturnMapper.java','dal/mysql/FulReturnItemMapper.java','dal/mysql/FulShipmentItemMapper.java','controller/admin/ReturnContracts.java','controller/admin/FulReturnController.java','service/FulReturnService.java','framework/ReturnFaultTestConfiguration.java','enums/FulfillmentErrors.java']]+['backend/yudao-module-fulfillment/src/main/resources/db/fulfillment/V4__return_receipt.sql','frontend/src/api/erp/fulfillment/index.ts','frontend/src/views/erp/fulfillment/FulfillmentReturns.vue','frontend/src/views/erp/fulfillment/FulfillmentWorkbench.vue']+['tests/'+x for x in ['m0_restart.py','m4_return_acceptance.py','m4_return_read_checks.py','m4_return_upgrade.py','m4_return_ui_fixture.py','m4_return_ui_assert.py','m4_return_frontend.ps1','m4_return_constraints.py','m4_return_restart.py','m4_return_qa.py']]
    check('source inventory unique',len(changed)==len(set(changed)))
    inventory=[]
    for name in changed:
        path=ROOT/name;check('source exists '+name,path.is_file())
        inventory.append({'path':name,'sha256':sha(path),'previous_M4_1_sha256':older.get(name,previous.get(name))})
        if name.endswith('.py'):
            py_compile.compile(str(path),doraise=True);check('Python compiles '+name,True)
    save('M4.2-changes.json',{'run_at':E['run_at'],'note':'Explicit M4.2 inventory, not a Git diff. Source hashes describe current delivery; earlier stages and iterative build evidence are retained separately.','count':len(inventory),'files':inventory})
    for name in docs:
        path=ROOT/name;body=path.read_text(encoding='utf-8')
        check('document UTF8 and fences '+name,'\ufffd' not in body and not body.startswith('\ufeff') and len(re.findall(r'^```',body,re.M))%2==0)
        for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)',body):
            target=unquote(target.strip('<>').split('#')[0])
            if not target or re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:',target):continue
            check('local link '+name+' -> '+target,(path.parent/target).exists())
    for name,size in [('desktop',(1280,900)),('mobile',(390,844))]:
        with Image.open(OUT/('M4.2-ui-'+name+'.jpg')) as pic:
            check('real browser JPEG '+name,pic.format=='JPEG' and pic.size==size,{'format':pic.format,'size':pic.size})
    layout=load('M4.2-ui-layout.json')
    check('recorded browser layout passed',layout['result']=='passed')
    for size in ['desktop','mobile']:
        val=layout[size];check('no page or form overflow '+size,val['bodyWidth']<=val['width'] and val['formWidth']<=val['sectionWidth'])
    target=ROOT/'backend/yudao-server/target/yudao-server.jar'
    check('running and final tested artifacts match',sha(target)==sha(ROOT/'.local/backend-run.jar')==sha(ROOT/'.local/m4-return-run.jar')==load('M4.2-final-api.json')['final_artifact_sha256'])
    runtime=load('M4.2-runtime.json')
    check('main and system listener inventory',set(x['LocalPort'] for x in runtime['listeners'])=={3306,15173,33306,36379,48080})
    check('all test listener ports free',runtime['test_ports_free'] and not runtime['test_listeners'])
    check('current main authentication',bool(M3Client().login().s.headers.get('Authorization')))
    check('current H R held and both ledgers agree',not sql('SELECT s.id FROM erp_stock s WHERE s.`count`<s.ful_reserved_count OR s.ful_reserved_count<0 OR s.ful_reserved_count<>(SELECT COALESCE(SUM(r.held_qty),0) FROM ful_reservation r WHERE r.tenant_id=s.tenant_id AND r.product_id=s.product_id AND r.warehouse_id=s.warehouse_id) OR s.ful_reserved_count<>(SELECT COALESCE(SUM(l.held_delta),0) FROM ful_stock_ledger l WHERE l.tenant_id=s.tenant_id AND l.product_id=s.product_id AND l.warehouse_id=s.warehouse_id) OR s.`count`<>(SELECT COALESCE(SUM(l.`count`),0) FROM erp_stock_record l WHERE l.tenant_id=s.tenant_id AND l.product_id=s.product_id AND l.warehouse_id=s.warehouse_id)'))
    check('current reserved shipped cancelled order aggregates',not sql('SELECT i.id FROM ful_order_item i WHERE i.reserved_qty<>(SELECT COALESCE(SUM(r.held_qty),0) FROM ful_reservation r WHERE r.tenant_id=i.tenant_id AND r.order_item_id=i.id) OR i.shipped_qty<>(SELECT COALESCE(SUM(s.quantity),0) FROM ful_shipment_item s WHERE s.tenant_id=i.tenant_id AND s.order_item_id=i.id) OR i.cancelled_qty<>(SELECT COALESCE(SUM(c.quantity),0) FROM ful_cancellation c WHERE c.tenant_id=i.tenant_id AND c.order_item_id=i.id)'))
    check('current returned order aggregate',not sql("SELECT i.id FROM ful_order_item i WHERE i.returned_qty<>(SELECT COALESCE(SUM(ri.quantity),0) FROM ful_return_item ri JOIN ful_return r ON r.id=ri.return_id AND r.tenant_id=ri.tenant_id WHERE ri.tenant_id=i.tenant_id AND ri.order_item_id=i.id AND r.status='RECEIVED')"))
    check('current pending and received within original allowance',not sql("SELECT s.id FROM ful_shipment_item s WHERE s.quantity<(SELECT COALESCE(SUM(i.quantity),0) FROM ful_return_item i JOIN ful_return r ON r.tenant_id=i.tenant_id AND r.id=i.return_id WHERE i.tenant_id=s.tenant_id AND i.shipment_item_id=s.id AND r.status IN ('REQUESTED','RECEIVED'))"))
    check('current received same source approved ERP document',not sql("SELECT r.id FROM ful_return r LEFT JOIN erp_sale_return e ON e.id=r.erp_sale_return_id AND e.tenant_id=r.tenant_id WHERE r.status='RECEIVED' AND (e.id IS NULL OR e.deleted<>0 OR e.status<>20 OR e.order_id<>(SELECT erp_order_id FROM ful_order WHERE id=r.order_id))"))
    check('current positive ERP physical receipt mappings',not sql("SELECT i.id FROM ful_return_item i JOIN ful_return r ON r.id=i.return_id LEFT JOIN erp_sale_return_items e ON e.id=i.erp_sale_return_item_id AND e.tenant_id=i.tenant_id LEFT JOIN erp_stock_record s ON s.id=i.erp_stock_record_id AND s.tenant_id=i.tenant_id WHERE r.status='RECEIVED' AND (e.id IS NULL OR s.id IS NULL OR e.return_id<>r.erp_sale_return_id OR e.`count`<>i.quantity OR e.warehouse_id<>r.warehouse_id OR s.`count`<>i.quantity OR s.biz_type<>60 OR s.biz_id<>r.erp_sale_return_id OR s.biz_item_id<>e.id)"))
    check('only received rows have physical mappings',not sql("SELECT i.id FROM ful_return_item i JOIN ful_return r ON r.id=i.return_id WHERE (r.status='RECEIVED')<>(i.erp_sale_return_item_id IS NOT NULL AND i.erp_stock_record_id IS NOT NULL)"))
    E['source_count']=len(inventory);E['status']='passed'
except Exception as error:
    E['status']='failed';E['error']=str(error);raise
finally:
    save('M4.2-final-qa.json',E)
    print('M4.2 final QA',E.get('status'),len(E['checks']),'checks; source files',E.get('source_count'))
