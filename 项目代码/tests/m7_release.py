"""M7.1 independent release reproduction on this host; no main business writes.
Fresh directory with spaces, schema, Redis DB9 and Broker vhost. Dependency
services are reused explicitly. Keeps owned release apps for a browser proof.
"""
import hashlib,json,os,re,shutil,socket,subprocess,time,zipfile
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import quote
import pymysql,requests
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'../学习资料/10-验收证据'
PREFIX=os.getenv('M7_DELIVERY_PREFIX','M7.1');REDIS_DB=int(os.getenv('M7_DELIVERY_REDIS','9'));FINAL=PREFIX!='M7.1'
assert PREFIX in ['M7.1','M7-final'] and REDIS_DB in [9,13]
RUN=datetime.now().strftime('%Y%m%d_%H%M%S');DATABASE='fulfillment_m7_release_'+RUN
BUILD=json.loads((ROOT/'.local/m7-release-build.json').read_text(encoding='utf-8-sig'));SOURCE=Path(BUILD['releaseDirectory'])
CLEAN=Path(os.environ['USERPROFILE'])/'fulfillment-delivery-tests'/('release '+RUN)
E={'run_at':datetime.now(timezone.utc).isoformat(),'database':DATABASE,'redis_database':REDIS_DB,'vhost':DATABASE,'release_directory':str(CLEAN),'package_directory':str(SOURCE),'checks':[],'commands':[],'boundary':'Fresh application directory and schema on the same Windows host; existing Java/Node/MySQL/Redis/RabbitMQ services reused.'}
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def check(name,ok,detail=None):
    E['checks'].append({'name':name,'passed':bool(ok),'detail':detail});print(('PASS ' if ok else 'FAIL ')+name,flush=True)
    if not ok:raise AssertionError(name+': '+str(detail))
def sql(query,args=(),database=None):
    with pymysql.connect(host='127.0.0.1',port=33306,user='fulfillment',password='fulfillment-dev',database=database or DATABASE,autocommit=True,charset='utf8mb4') as con:
        with con.cursor() as cur:cur.execute(query,args);return cur.fetchall()
def wait(fn,seconds=110):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        try:
            result=fn()
            if result:return result
        except requests.RequestException:pass
        time.sleep(.3)
    raise AssertionError('Timed out waiting for release')
def free(port):
    with socket.socket() as s:return s.connect_ex(('127.0.0.1',port))!=0
def shell(script,*args,expected=0):
    log=ROOT/'.local'/('m7-release-'+RUN+'-'+str(len(E['commands']))+'.log')
    with log.open('wb') as out:r=subprocess.run([os.getenv('M0_PWSH','pwsh'),'-NoProfile','-File',str(CLEAN/'bin'/script),*map(str,args)],cwd=CLEAN,stdout=out,stderr=subprocess.STDOUT,timeout=210)
    E['commands'].append({'script':script,'arguments':[str(x) for x in args],'exit_code':r.returncode,'log':str(log.relative_to(ROOT))});check(script+(' rejects' if expected else ' exits0'),r.returncode!=0 if expected else r.returncode==0)
    return log.read_text(encoding='utf-8',errors='replace')
def node_demo():
    log=ROOT/'.local'/('m7-release-'+RUN+'-demo-'+str(len(E['commands']))+'.log')
    with log.open('wb') as out:r=subprocess.run([shutil.which('node'),str(CLEAN/'bin/Seed-Demo.cjs'),str(CLEAN/'config.local.json')],cwd=CLEAN,stdout=out,stderr=subprocess.STDOUT,timeout=210)
    E['commands'].append({'script':'Seed-Demo.cjs','exit_code':r.returncode,'log':str(log.relative_to(ROOT))});check('self-contained Node demo exits0',r.returncode==0)
    return log.read_text(encoding='utf-8',errors='replace')
def facts(database=None):
    tables=['erp_stock','erp_stock_record','ful_order','ful_order_item','ful_reservation','ful_stock_ledger','ful_shipment','ful_shipment_item','ful_cancellation','ful_return','ful_return_item','erp_sale_order','erp_sale_order_items','erp_sale_out','erp_sale_out_items','erp_sale_return','erp_sale_return_items']
    return {t:sql('SELECT * FROM '+t+' ORDER BY id',database=database) for t in tables}
def digest(value):return hashlib.sha256(json.dumps(value,default=str,sort_keys=True).encode()).hexdigest()
def snapshot():
    tables=[r[0] for r in sql("SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND LEFT(TABLE_NAME,4)='ful_'")]
    return {'business':digest(facts()),'fulfillment':{t:sql('SELECT * FROM '+t+' ORDER BY '+('installed_rank' if t=='ful_flyway_schema_history' else 'tenant_id' if t=='ful_job_gate' else 'id')) for t in sorted(tables)}}
def private_files():
    result=[]
    for ident,key,size,hash_ in sql('SELECT id,storage_key,byte_size,sha256 FROM ful_private_file ORDER BY id'):
        p=CLEAN/'data/files'/key;assert p.stat().st_size==size and sha(p)==hash_;result.append([ident,key,size,hash_])
    return result
def client(name='admin'):
    s=requests.Session();s.headers['tenant-id']='1';r=s.post('http://127.0.0.1:15174/admin-api/system/auth/login',json={'username':name,'password':'admin123'},timeout=25);r.raise_for_status();body=r.json();assert body['code']==0,body;s.headers['Authorization']='Bearer '+body['data']['accessToken'];return s
def api(s,method,path,body=None,headers=None,ok=True):
    response=s.request(method,'http://127.0.0.1:15174/admin-api'+path,json=body,headers=headers,timeout=45);response.raise_for_status();result=response.json()
    if ok:assert result['code']==0,result;return result['data']
    return result
def main():
    expected=json.loads((OUT/('M7-build.json' if FINAL else 'M6-build.json')).read_text(encoding='utf-8'))
    expected_sha=expected['backend_sha256'] if FINAL else expected['artifacts']['.local/backend-run.jar']
    check('source bundle matches selected verified backend',BUILD['backendSha256']==sha(ROOT/'backend/yudao-server/target/yudao-server.jar')==expected_sha)
    check('test application ports free',free(48082) and free(15174))
    redis=next((ROOT/'.local/tools').rglob('redis-cli.exe'));probe=subprocess.run([str(redis),'-h','127.0.0.1','-p','36379','-n',str(REDIS_DB),'DBSIZE'],capture_output=True,text=True,timeout=10)
    check('dedicated Redis DB starts empty',probe.returncode==0 and probe.stdout.strip()=='0')
    manifest=json.loads((SOURCE/'manifest.json').read_text(encoding='utf-8-sig'));check('all source package hashes verified',all(sha(SOURCE/x['path'])==x['sha256'] for x in manifest['files']))
    check('package carries no node_modules target or live config',not any(set(Path(x['path']).parts)&{'node_modules','target','.local','config.local.json'} for x in manifest['files']))
    main_before=digest(facts('fulfillment'));E['main_before_digest']=main_before
    total=sum(p.stat().st_size for p in SOURCE.rglob('*') if p.is_file());disk=shutil.disk_usage(Path(os.environ['USERPROFILE']))
    check('preflight capacity for fresh copy and ZIP',disk.free>total*3,{'bytes':total,'files':len(manifest['files'])+1,'free_bytes':disk.free})
    check('fresh clean-room destination outside source',not CLEAN.exists() and not CLEAN.resolve().is_relative_to(ROOT.resolve()))
    CLEAN.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(SOURCE,CLEAN)
    check('copied package byte-identical',all(sha(CLEAN/x['path'])==x['sha256'] for x in manifest['files']))
    c=json.loads((CLEAN/'bin/config.example.json').read_text(encoding='utf-8'));c.update(database=DATABASE,rabbitVhost=DATABASE,redisDatabase=REDIS_DB);(CLEAN/'config.local.json').write_text(json.dumps(c,indent=2)+'\n',encoding='utf-8')
    broker='http://127.0.0.1:35673/api';auth=('fulfillment','fulfillment-mq-dev');encoded=quote(DATABASE,safe='')
    check('isolated Broker vhost created',requests.put(broker+'/vhosts/'+encoded,auth=auth,json={},timeout=10).status_code in [201,204]);check('isolated vhost user permissions',requests.put(broker+'/permissions/'+encoded+'/fulfillment',auth=auth,json={'configure':'.*','read':'.*','write':'.*'},timeout=10).status_code in [201,204])
    probe=CLEAN/'bin/serve.cjs';original=probe.read_bytes()
    try:
        probe.write_bytes(original+b'\n// deliberate clean-room integrity probe\n');body=shell('Start-Release.ps1','-Config',CLEAN/'config.local.json',expected=1)
        check('tampered package rejected before processes start','Release hash mismatch' in body and free(48082) and free(15174))
    finally:probe.write_bytes(original)
    os.environ['DB_ADMIN_PASSWORD']='local-root-dev'
    try:shell('Install-Release.ps1','-Config',CLEAN/'config.local.json','-MysqlClient',ROOT/'.local/tools/mysql-8.4.6-winx64/bin/mysql.exe')
    finally:os.environ.pop('DB_ADMIN_PASSWORD',None)
    check('clean install has current immutable migrations',tuple(r[0] for r in sql('SELECT version FROM ful_flyway_schema_history ORDER BY installed_rank'))==tuple(str(n) for n in range(9 if FINAL else 8)))
    check('new business schema initially empty',all(not x for x in facts().values()))
    shell('Start-Release.ps1','-Config',CLEAN/'config.local.json');wait(lambda:requests.get('http://127.0.0.1:15174',timeout=2).status_code==200)
    body=node_demo();check('demo completes from package only','M7_DEMO_READY' in body)
    demo=json.loads((CLEAN/'data/demo.json').read_text(encoding='utf-8'));E['demo']=demo;ids=demo['ids'];order=ids['bound']['orderId'];product=ids['product'];a=ids['warehouseA'];b=ids['warehouseB']
    check('actual multi-warehouse final balances',sql('SELECT warehouse_id,`count`,ful_reserved_count FROM erp_stock WHERE product_id=%s ORDER BY warehouse_id',(product,))==((a,4,0),(b,8,0)))
    check('gross shipped cancellation return aggregates exact',sql('SELECT ordered_qty,open_qty,reserved_qty,shipped_qty,cancelled_qty,returned_qty FROM ful_order_item WHERE order_id=%s',(order,))==((10,0,0,4,6,2),))
    check('shipment signed callback delivered',sql('SELECT status FROM ful_shipment WHERE id=%s',(ids['shipped']['shipmentId'],))==(('DELIVERED',),))
    check('repeated file task has one real draft identity',sql('SELECT COUNT(*) FROM ful_import_identity WHERE source_system=%s',(demo['source'],))==((1,),) and sql("SELECT COUNT(*) FROM ful_file_job_row WHERE job_id=%s AND outcome='EXISTING'",(ids['duplicateImport']['jobId'],))==((1,),))
    check('two imports each localize the bad row',sql("SELECT success_rows,failed_rows,status FROM ful_file_job WHERE job_type='IMPORT' ORDER BY id")==((1,1,'PARTIAL_FAILED'),(1,1,'PARTIAL_FAILED')))
    wait(lambda:sql("SELECT COUNT(*) FROM ful_outbox_event WHERE status<>'SENT'")[0][0]==0 and sql("SELECT COUNT(*) FROM ful_outbox_event o LEFT JOIN ful_inbox_event i ON i.event_id=o.event_id AND i.tenant_id=o.tenant_id WHERE i.id IS NULL OR i.status<>'PROCESSED'")[0][0]==0)
    check('same-origin messages and current projection complete',sql('SELECT observed_version FROM ful_order_read_model WHERE order_id=%s',(order,))[0][0]==sql('SELECT version FROM ful_order WHERE id=%s',(order,))[0][0])
    check('real XLSX and localized error file saved',zipfile.is_zipfile(CLEAN/'data/demo-stock.xlsx') and b'QUANTITY_MUST_BE_POSITIVE' in (CLEAN/'data/demo-error.csv').read_bytes())
    check('private registered files match bytes',len(private_files())>=4)
    s=client();limited=client('m7warehouse');scope=api(limited,'GET','/fulfillment/warehouse/scope')
    check('warehouse demo user sees only READ XiAn',scope==[{'id':str(a),'name':'演示西安仓','canOperate':False}])
    check('warehouse user cannot access other warehouse',api(limited,'GET','/fulfillment/warehouse/stock-page?warehouseId='+str(b),ok=False)['code']==1080000075)
    check('warehouse user cannot request sales prices',api(limited,'GET','/fulfillment/order/get?id='+order,ok=False)['code']==403)
    check('private storage and local config not served',all(requests.get('http://127.0.0.1:15174/'+name,timeout=5).status_code==404 for name in ['config.local.json','data/files/'+private_files()[0][1]]))
    bad=requests.post('http://127.0.0.1:15174/app-api/fulfillment/logistics/callback/not-configured',json={},timeout=10)
    check('app-api proxy reaches signed callback validation',bad.headers.get('content-type','').startswith('application/json') and bad.json()['code']!=0)
    index=requests.get('http://127.0.0.1:15174/erp/fulfillment',timeout=10);assets=re.findall(r'<script[^>]+src="([^"]+)"',index.text)
    check('production SPA deep link and module asset served',index.status_code==200 and assets and all(requests.get('http://127.0.0.1:15174'+p,timeout=10).status_code==200 for p in assets))
    finish(demo,main_before)

def finish(demo,main_before):
    ids=demo['ids'];order=ids['bound']['orderId']
    snap=snapshot();registered=private_files();before=digest(snap)
    os.environ['DB_ADMIN_PASSWORD']='local-root-dev'
    try:body=shell('Install-Release.ps1','-Config',CLEAN/'config.local.json','-MysqlClient',ROOT/'.local/tools/mysql-8.4.6-winx64/bin/mysql.exe',expected=1)
    finally:os.environ.pop('DB_ADMIN_PASSWORD',None)
    check('existing database refuses reinstall without fact changes','Database exists' in body and digest(snapshot())==before)
    shell('Stop-Release.ps1');wait(lambda:free(48082) and free(15174),30);shell('Start-Release.ps1','-Config',CLEAN/'config.local.json');wait(lambda:requests.get('http://127.0.0.1:15174',timeout=2).status_code==200)
    check('normal application restart preserves full fulfillment and business snapshot',digest(snapshot())==before)
    check('restart preserves every registered private file',private_files()==registered)
    check('completed fixed demo rerun only reads saved IDs','M7_DEMO_REUSED' in node_demo() and digest(snapshot())==before)
    s=client();replayed=api(s,'POST','/fulfillment/order/bind',{'erpOrderId':str(ids['sourceOrder'])},headers={'Idempotency-Key':demo['keys']['bind']})
    check('original business key replay after restart immutable',replayed==ids['bound'] and digest(snapshot())==before)
    check('main 17-table business digest untouched',digest(facts('fulfillment'))==main_before)
    E.update(main_after_digest=digest(facts('fulfillment')),backend_sha256=sha(CLEAN/'app/backend.jar'),manifest_sha256=sha(CLEAN/'manifest.json'),result='passed',browser_pending=True,release_processes_stopped=False)
try:
    if os.getenv('M7_RELEASE_RESUME'):
        previous=Path(os.environ['M7_RELEASE_RESUME']);saved=json.loads(previous.read_text(encoding='utf-8'));assert saved['result']=='failed' and saved['error']=='not enough arguments for format string'
        assert all(x['passed'] for x in saved['checks'])
        E=saved;E['resumed_at']=datetime.now(timezone.utc).isoformat();E['resume_of']=str(previous);E.pop('error',None);E['result']='running'
        DATABASE=E['database'];CLEAN=Path(E['release_directory']);SOURCE=Path(E['package_directory'])
        assert DATABASE.startswith('fulfillment_m7_release_') and CLEAN.resolve().is_relative_to((Path(os.environ['USERPROFILE'])/'fulfillment-delivery-tests').resolve())
        check('resumed original unchanged copied release',all(sha(CLEAN/x['path'])==x['sha256'] for x in json.loads((CLEAN/'manifest.json').read_text(encoding='utf-8-sig'))['files']))
        shell('Start-Release.ps1','-Config',CLEAN/'config.local.json');wait(lambda:requests.get('http://127.0.0.1:15174',timeout=2).status_code==200)
        finish(E['demo'],E['main_before_digest'])
    else:main()
except Exception as error:
    E.update(result='failed',error=str(error))
    if(CLEAN/'data/processes.json').exists():
        try:shell('Stop-Release.ps1')
        except Exception:pass
    raise
finally:
    target=OUT/(PREFIX+'-release.json' if E.get('result')=='passed' else PREFIX+'-failed-'+RUN+'.json');target.write_text(json.dumps(E,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
    print(PREFIX+' release',E.get('result'),len(E['checks']),'checks',flush=True)
