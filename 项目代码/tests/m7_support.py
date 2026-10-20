"""Shared M7 execution helpers. Isolated schemas, bounded JVMs, owned cleanup."""
import hashlib,json,os,shutil,socket,subprocess,time
from datetime import datetime,timezone
from pathlib import Path
import pymysql,requests
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'../学习资料/10-验收证据';JAR=ROOT/'backend/yudao-server/target/yudao-server.jar'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(name,data):(OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
def load(name):return json.loads((OUT/name).read_text(encoding='utf-8-sig'))
def sql(database,query,args=()):
    assert database.startswith('fulfillment_m7_') or database=='fulfillment'
    with pymysql.connect(host='127.0.0.1',port=33306,user='fulfillment',password='fulfillment-dev',database=database,charset='utf8mb4',autocommit=True) as c:
        with c.cursor() as cur:cur.execute(query,args or None);return cur.fetchall()
def free(port):
    with socket.socket() as s:return s.connect_ex(('127.0.0.1',port))!=0
def wait(fn,seconds=120):
    until=time.monotonic()+seconds
    while time.monotonic()<until:
        try:
            result=fn()
            if result:return result
        except requests.RequestException:pass
        time.sleep(.25)
    raise AssertionError('Timed out')
def shell(file,*args,label='m7-command'):
    log=ROOT/'.local'/(label+'-'+str(time.time_ns())+'.log')
    with log.open('wb') as out:r=subprocess.run([os.getenv('M0_PWSH','pwsh'),'-NoProfile','-File',str(ROOT/file),*map(str,args)],cwd=ROOT,stdout=out,stderr=subprocess.STDOUT,timeout=180)
    if r.returncode:raise AssertionError(str(file)+' failed; '+str(log))
    return {'script':str(file),'args':args,'exit_code':r.returncode,'log':str(log.relative_to(ROOT))}
def initialize(database):
    assert database.startswith('fulfillment_m7_')
    result=[shell('scripts/Initialize-Database.ps1','-Database',database,label='m7-'+database)]
    result += [shell('scripts/Migrate-Database.ps1','-Action',a,'-Database',database,label='m7-'+database) for a in ['baseline','migrate','validate']]
    return result
class Client:
    def __init__(self,port,tenant=1):self.base='http://127.0.0.1:'+str(port)+'/admin-api';self.s=requests.Session();self.s.headers['tenant-id']=str(tenant)
    def api(self,method,path,body=None,params=None,key=None,ok=True):
        response=self.s.request(method,self.base+path,json=body,params=params,headers={'Idempotency-Key':key} if key else None,timeout=90);response.raise_for_status();data=response.json()
        if ok:assert data['code']==0,data;return data['data']
        return data
    def login(self,name='admin'):
        token=self.api('POST','/system/auth/login',{'username':name,'password':'admin123'});self.s.headers['Authorization']='Bearer '+token['accessToken'];return self
class Runtime:
    def __init__(self,database,redis=12):self.database=database;self.redis=redis;self.owned=[]
    def start(self,port,label,properties=None,jar=None):
        assert free(port) and port!=48080
        env=os.environ.copy();env.update(DB_NAME=self.database,APP_PORT=str(port));dest=ROOT/'.local'/('m7-'+label+'.jar');shutil.copyfile(jar or JAR,dest)
        props={'spring.profiles.active':'fulfillment','server.port':str(port),'spring.data.redis.database':str(self.redis),'fulfillment.expiry.enabled':'false','fulfillment.jobs.enabled':'false','fulfillment.messages.enabled':'false','logging.file.name':str(ROOT/'.local'/('m7-'+label+'-app.log'))}
        props.update(properties or {});log=ROOT/'.local'/('m7-'+label+'-out.log');out=log.open('wb')
        p=subprocess.Popen([shutil.which('java'),'-Xms128m','-Xmx768m','-Dfile.encoding=UTF-8','-Duser.timezone=Asia/Shanghai','-jar',str(dest)]+['--'+k+'='+str(v) for k,v in props.items()],cwd=ROOT/'backend',env=env,stdout=out,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW);self.owned.append((p,out,log))
        def ready():
            if p.poll() is not None:raise AssertionError('JVM exited '+label)
            try:return Client(port).login()
            except requests.RequestException:return False
        wait(ready);return p
    def stop(self,p):
        if p.poll() is None:
            p.terminate()
            try:p.wait(25)
            except subprocess.TimeoutExpired:p.kill();p.wait(10)
    def close(self):
        for p,out,_ in self.owned:self.stop(p);out.close()
        return all(p.poll() is not None for p,_,_ in self.owned)
