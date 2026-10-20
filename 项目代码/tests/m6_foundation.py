"""M6.1 real schema/job admission/cancel/process-recovery acceptance.
Creates an isolated schema; deliberately leaves input/result files for evidence.
"""
import hashlib,json,os,shutil,socket,subprocess,time,uuid
from datetime import datetime,timezone
DATABASE=os.getenv('M6_DATABASE','fulfillment_m6_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
os.environ['DB_NAME']=DATABASE;os.environ['M4_RETURN_DATABASE']=DATABASE
import m4_return_acceptance as b
from m1_acceptance import ROOT,sql,db
RUN='M6'+uuid.uuid4().hex[:8];JAR=ROOT/'.local/m6-test.jar';OWNED=[]
E={'run_at':datetime.now(timezone.utc).isoformat(),'database':DATABASE,'redis_database':8,'checks':[],'commands':[],'processes':[]}
def check(name,ok,detail=None):
    E['checks'].append({'name':name,'passed':bool(ok),'detail':detail});print(('PASS ' if ok else 'FAIL ')+name,flush=True)
    if not ok:raise AssertionError(name+': '+str(detail))
def wait(fn,seconds=100):return b.wait_for(fn,seconds)
def shell(file,*args):
    path=ROOT/'.local'/('m6-'+DATABASE+'-setup-'+str(len(E['commands']))+'.log')
    with path.open('wb') as out:r=subprocess.run([os.environ['M0_PWSH'],'-NoProfile','-File',str(ROOT/file),*args],cwd=ROOT,stdout=out,stderr=subprocess.STDOUT,timeout=180)
    E['commands'].append({'file':file,'arguments':args,'exit_code':r.returncode,'log':str(path.relative_to(ROOT))});check('setup '+file+' '+str(args),r.returncode==0)
class Client(b.Client):
    def job(self,id,ok=True):return self.api('GET','/fulfillment/job/get',params={'id':str(id)},ok=ok)
    def export(self,dataset='STOCK',warehouses=None,key=None,ok=True,**extra):return self.api('POST','/fulfillment/job/export',{'dataset':dataset,'warehouseIds':[str(x) for x in warehouses or []],**extra},headers={'Idempotency-Key':key or uuid.uuid4().hex},ok=ok)
    def control(self,id,retry=False,key=None,ok=True,reason='M6受控恢复'):
        return self.api('POST','/fulfillment/job/'+('retry' if retry else 'cancel'),{'jobId':str(id),'reason':reason},headers={'Idempotency-Key':key or uuid.uuid4().hex},ok=ok)
    def upload(self,data,name='input.csv',ok=True):
        response=self.s.post(self.base+'/fulfillment/job/upload',files={'file':(name,data,'text/csv')},timeout=30);response.raise_for_status();body=response.json()
        if ok:
            assert body['code']==0,body;return body['data']
        return body
    def import_file(self,id,source=RUN,key=None,ok=True):return self.api('POST','/fulfillment/job/import',{'fileId':id,'sourceSystem':source},headers={'Idempotency-Key':key or uuid.uuid4().hex},ok=ok)
    def download(self,id,kind='RESULT'):
        return self.s.get(self.base+'/fulfillment/job/download',params={'id':str(id),'kind':kind},timeout=40)
def start(label,port=48083,worker=False,options=()):
    env=os.environ.copy();env['APP_PORT']=str(port)
    props={'spring.profiles.active':'fulfillment'+(',fulfillment-file-test' if options else ''),'spring.data.redis.database':'8','fulfillment.expiry.enabled':'false','fulfillment.messages.enabled':'false','fulfillment.jobs.enabled':str(worker).lower(),'fulfillment.jobs.workers':'1','fulfillment.jobs.queue-capacity':'1','fulfillment.jobs.tenant-concurrency':'1','fulfillment.jobs.tenant-pending-limit':'3','fulfillment.jobs.global-pending-limit':'6','fulfillment.jobs.lease-seconds':'5','fulfillment.jobs.batch-size':'2','fulfillment.jobs.delay-ms':'200','fulfillment.jobs.initial-delay-ms':'1000','fulfillment.jobs.storage-root':str(ROOT/'.local/fulfillment-files'/DATABASE),'logging.file.name':'../.local/m6-'+label+'-app.log'}
    for value in options:
        key,content=value.removeprefix('--').split('=',1);props[key]=content
    args=[shutil.which('java'),'-Xms128m','-Xmx768m','-Dfile.encoding=UTF-8','-Duser.timezone=Asia/Shanghai','-jar',str(JAR)]+['--'+key+'='+value for key,value in props.items()]
    out=(ROOT/'.local'/('m6-'+label+'-out.log')).open('wb');p=subprocess.Popen(args,cwd=ROOT/'backend',env=env,stdout=out,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW);OWNED.append((p,out));E['processes'].append({'label':label,'pid':p.pid,'port':port,'worker':worker,'options':options})
    def ready():
        if p.poll() is not None:
            if p.returncode in [80,81,82] and any('job-crash=' in x for x in options):return True
            raise AssertionError('Unexpected process exit '+label+' '+str(p.returncode))
        try:return Client(port).login()
        except Exception:return False
    wait(ready);return p
def stop(p):b.stop(p)
def state(id):return sql('SELECT status,lease_version FROM ful_file_job WHERE id=%s',(id,))[0]
def business():return {t:sql('SELECT * FROM '+t+' ORDER BY id') for t in ['erp_stock','erp_stock_record','ful_order','ful_order_item','ful_reservation','ful_stock_ledger','ful_shipment','ful_shipment_item','ful_cancellation','ful_return','ful_return_item','erp_sale_order','erp_sale_order_items','erp_sale_out','erp_sale_out_items','erp_sale_return','erp_sale_return_items']}
def main():
    for port in [48082,48083]:
        with socket.socket() as s:check('isolated port free '+str(port),s.connect_ex(('127.0.0.1',port))!=0)
    shell('scripts/Initialize-Database.ps1','-Database',DATABASE)
    for action in ['baseline','migrate','validate']:shell('scripts/Migrate-Database.ps1','-Action',action,'-Database',DATABASE)
    check('history V0 through V7',tuple(x[0] for x in sql('SELECT version FROM ful_flyway_schema_history ORDER BY installed_rank'))==tuple(str(v) for v in range(8)))
    shutil.copyfile(ROOT/'backend/yudao-server/target/yudao-server.jar',JAR);E['artifact_sha256']=hashlib.sha256(JAR.read_bytes()).hexdigest()
    api=start('foundation-api',48082);c=Client(48082).login();f=b.Fixture(c,'Foundation');fx=f.shipment('基础',('1',));E['fixture']=fx
    key='submit-'+RUN;one=c.export(warehouses=[f.w],key=key);check('same export key stable',c.export(warehouses=[f.w],key=key)==one)
    two=c.export(warehouses=[f.w]);three=c.export(warehouses=[f.w]);check('database pending capacity rejects fourth',c.export(warehouses=[f.w],key='full-'+RUN,ok=False)['code']==1080000071)
    check('rejected admission leaves no command',not sql('SELECT id FROM ful_command_record WHERE idempotency_key=%s',('full-'+RUN,)))
    cancel_key='cancel-'+RUN;cancel=c.control(two['jobId'],key=cancel_key);check('pending job cancelled immediately',cancel['outcome']=='CANCELLED' and state(two['jobId'])[0]=='CANCELLED');check('cancel key stable',c.control(two['jobId'],key=cancel_key)==cancel)
    check('cancel reason conflict same key',c.control(two['jobId'],key=cancel_key,reason='不同意图',ok=False)['code']==1080000005)
    four=c.export(warehouses=[f.w],key='full-'+RUN);check('same formerly rejected key works after capacity freed',four['outcome']=='EXPORT_QUEUED')
    c.control(three['jobId']);c.control(four['jobId']);before=business();worker=start('foundation-worker',worker=True)
    wait(lambda:state(one['jobId'])[0]=='SUCCEEDED');check('worker generated private result',c.job(one['jobId'])['hasResult'])
    check('export changed no business facts',business()==before)
    runtime=Client(48083).login().api('GET','/fulfillment/job/runtime');check('bounded executor actual capacities',runtime['enabled'] and runtime['instance']['workers']==runtime['instance']['queueCapacity']==1)
    download=c.download(one['jobId']);check('authorized real XLSX download',download.status_code==200 and download.content.startswith(b'PK') and 'no-store' in download.headers.get('Cache-Control',''))
    stop(worker)
    crash_job=c.export(warehouses=[f.w]);crash=start('foundation-crash',worker=True,options=('--fulfillment.test.job-crash=AFTER_CLAIM','--fulfillment.test.job-target='+crash_job['jobId']))
    wait(lambda:crash.poll() is not None);check('actual process exit after claim',crash.returncode==80 and 'M6_CRASH_AFTER_CLAIM' in (ROOT/'.local/m6-foundation-crash-out.log').read_text(encoding='utf-8',errors='replace'))
    check('claimed task retained for lease recovery',state(crash_job['jobId'])[0]=='RUNNING')
    recovery=start('foundation-recovery',worker=True);wait(lambda:state(crash_job['jobId'])[0]=='SUCCEEDED');check('reclaimed with higher fencing version',state(crash_job['jobId'])[1]>=2 and c.job(crash_job['jobId'])['totalAttempts']==2)
    check('recovery still changes no business facts',business()==before);E['export']=one;E['crash_job']=crash_job;E['result']='passed'
if __name__=='__main__':
    try:main()
    except Exception as error:E['result']='failed';E['error']=str(error);raise
    finally:
        for p,out in OWNED:stop(p);out.close()
        E['all_owned_processes_stopped']=all(p.poll() is not None for p,_ in OWNED)
        prefix='M6.1-' if E.get('result')=='passed' else 'M6.1-failed-'+DATABASE+'-'
        for p in (ROOT/'.local').glob('m6-foundation-*-out.log'):shutil.copyfile(p,ROOT/'../学习资料/10-验收证据'/(prefix+p.name))
        (ROOT/'../学习资料/10-验收证据'/(('M6.1-foundation.json') if E.get('result')=='passed' else prefix+'result.json')).write_text(json.dumps(E,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
        print('M6.1',E.get('result'),len(E['checks']),'checks',DATABASE,flush=True)
