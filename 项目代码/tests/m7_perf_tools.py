"""Raw timed HTTP and sampled JVM/SQL metrics; no global SQL stat reset."""
import concurrent.futures,math,os,shutil,subprocess,threading,time
import psutil,pymysql
from pathlib import Path

def cpu_model():
    import winreg
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:
        return winreg.QueryValueEx(key,'ProcessorNameString')[0].strip()

def root_sql(query,args=()):
    with pymysql.connect(host='127.0.0.1',port=33306,user='root',password='local-root-dev',autocommit=True) as con:
        with con.cursor() as c:c.execute(query,args or None);return c.fetchall()
def digest_stats(database):
    rows=root_sql("SELECT DIGEST,DIGEST_TEXT,COUNT_STAR,SUM_ROWS_EXAMINED,SUM_TIMER_WAIT FROM performance_schema.events_statements_summary_by_digest WHERE SCHEMA_NAME=%s AND LOWER(DIGEST_TEXT) LIKE 'select%%' AND LOWER(DIGEST_TEXT) LIKE '%%ful_order%%'",(database,))
    return {r[0]:{'sql':r[1],'count':int(r[2]),'rows_examined':int(r[3]),'timer_ps':int(r[4])} for r in rows}
def delta_stats(a,b):
    return [{'digest':k,'sql':v['sql'],**{n:v[n]-a.get(k,{}).get(n,0) for n in ['count','rows_examined','timer_ps']}} for k,v in b.items() if v['count']>a.get(k,{}).get('count',0)]
def summary(rows,seconds):
    values=sorted(x['ms'] for x in rows);percent=lambda p:values[min(len(values)-1,math.ceil(len(values)*p)-1)]
    return {'samples':len(rows),'seconds':seconds,'requests_per_second':len(rows)/seconds,'p50_ms':percent(.5),'p95_ms':percent(.95),'p99_ms':percent(.99),'errors':sum(not r['ok'] for r in rows)}
def parallel(work,items,concurrency):
    started=time.perf_counter()
    def timed(item):
        t=time.perf_counter()
        try:result=work(item);return {'item':item,'ms':(time.perf_counter()-t)*1000,'ok':True,'result':result}
        except Exception as e:return {'item':item,'ms':(time.perf_counter()-t)*1000,'ok':False,'error':str(e)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:rows=list(pool.map(timed,items))
    return rows,summary(rows,time.perf_counter()-started)

class Sample:
    def __init__(self,pid):self.pid=pid;self.stop=threading.Event();self.rows=[];self.process=psutil.Process(pid);self.jstat=str(Path(shutil.which('java')).parent/'jstat.exe')
    def gc(self):
        r=subprocess.run([self.jstat,'-gc',str(self.pid)],capture_output=True,text=True,timeout=8,creationflags=subprocess.CREATE_NO_WINDOW)
        lines=r.stdout.strip().splitlines()
        if r.returncode or len(lines)<2:raise AssertionError('jstat sampling failed '+r.stderr)
        return dict(zip(lines[0].split(),[float(v) if v!='-' else 0 for v in lines[1].split()]))
    def __enter__(self):
        self.before=self.gc();self.cpu=self.process.cpu_times();self.t=time.monotonic()
        def collect():
            while not self.stop.is_set():
                g=self.gc();self.rows.append({'offset_s':time.monotonic()-self.t,'rss_bytes':self.process.memory_info().rss,'heap_used_kib':sum(g.get(k,0) for k in ['S0U','S1U','EU','OU']),'gc':g});self.stop.wait(.5)
        self.thread=threading.Thread(target=collect,daemon=True);self.thread.start();return self
    def __exit__(self,*args):
        self.stop.set();self.thread.join(12);self.after=self.gc();cpu=self.process.cpu_times();seconds=time.monotonic()-self.t
        self.result={'sample_interval_s':.5,'heap_peak_is_sampled_not_exact':True,'gc_before':self.before,'gc_after':self.after,'gc_delta':{k:self.after.get(k,0)-self.before.get(k,0) for k in ['YGC','FGC','CGC','GCT']},'elapsed_s':seconds,'cpu_core_percent':100*((cpu.user+cpu.system)-(self.cpu.user+self.cpu.system))/seconds,'rss_peak_bytes':max((r['rss_bytes'] for r in self.rows),default=0),'heap_sample_peak_kib':max((r['heap_used_kib'] for r in self.rows),default=0),'raw':self.rows}
