"""Start/stop owned M4.3 isolated UI runtime and execute legacy regressions.
No corruption here: browser uses preserved historical reports from core tests.
"""
import hashlib,json,os,shutil,socket,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];META=ROOT/'.local/m4-reconcile-ui-runtime.json'
core=json.loads((ROOT/'../学习资料/10-验收证据/M4.3-reconcile-acceptance.json').read_text(encoding='utf-8'))
def digest(database):
    import pymysql
    tables=['erp_stock','erp_stock_record','ful_order','ful_order_item','ful_reservation','ful_stock_ledger','ful_shipment','ful_shipment_item','ful_cancellation','ful_return','ful_return_item','erp_sale_order','erp_sale_order_items','erp_sale_out','erp_sale_out_items','erp_sale_return','erp_sale_return_items']
    with pymysql.connect(host='127.0.0.1',port=33306,user='fulfillment',password='fulfillment-dev',database=database) as con:
        with con.cursor() as cur:
            rows={}
            for table in tables:cur.execute('SELECT * FROM '+table+' ORDER BY id');rows[table]=cur.fetchall()
    return hashlib.sha256(json.dumps(rows,default=str,sort_keys=True).encode()).hexdigest()
def wait(port,timeout=75):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        with socket.socket() as s:
            if s.connect_ex(('127.0.0.1',port))==0:return
        time.sleep(.3)
    raise AssertionError('Listener did not start '+str(port))
def launch(args,label,cwd,env):
    with (ROOT/'.local'/('m4-reconcile-ui-'+label+'.log')).open('wb') as out:
        p=subprocess.Popen(args,cwd=cwd,env=env,stdout=out,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    return p.pid
if __name__=='__main__':
    if sys.argv[1]=='start':
        assert core['result']=='passed' and core['all_owned_processes_stopped']
        for port in [48082,15174]:
            with socket.socket() as s:assert s.connect_ex(('127.0.0.1',port))!=0
        jar=ROOT/'.local/m4-reconcile-ui.jar';shutil.copyfile(ROOT/'backend/yudao-server/target/yudao-server.jar',jar)
        env=os.environ.copy();env.update(DB_NAME=core['database'],APP_PORT='48082')
        data={'database':core['database'],'expected_jar':str(jar),'expected_vite':str(ROOT/'frontend/node_modules/vite/bin/vite.js')}
        data['backend_pid']=launch([shutil.which('java'),'-Xms128m','-Xmx768m','-Dfile.encoding=UTF-8','-jar',str(jar),'--spring.profiles.active=fulfillment','--spring.data.redis.database=6','--logging.file.name=../.local/m4-reconcile-ui-app.log'],'backend',ROOT/'backend',env)
        META.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');wait(48082)
        env['API_BASE']='http://127.0.0.1:48082'
        for script,var,name in [('m1_acceptance.py','M1_EVIDENCE','M4.3-clean-binding.json'),('m0_smoke.py','M0_EVIDENCE','M4.3-ERP-regression.json')]:
            env[var]=name
            with (ROOT/'.local'/('m4-reconcile-ui-'+script+'.log')).open('wb') as out:r=subprocess.run([sys.executable,str(ROOT/'tests'/script)],env=env,stdout=out,stderr=subprocess.STDOUT,timeout=160)
            assert r.returncode==0,script
        env['VITE_BASE_URL']='http://127.0.0.1:48082'
        data['frontend_pid']=launch([shutil.which('node'),'--max-old-space-size=4096',data['expected_vite'],'--mode','fulfillment','--port','15174','--host','127.0.0.1','--strictPort'],'frontend',ROOT/'frontend',env)
        data['before_core_digest']=digest(core['database']);data['before_main_digest']=digest('fulfillment')
        META.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');wait(15174);print('Isolated UI ready http://127.0.0.1:15174')
    elif sys.argv[1]=='stop':
        data=json.loads(META.read_text(encoding='utf-8'))
        # Pass exact PID and expected executable argument as data, never compose
        # shell deletion strings or kill arbitrary port owners.
        for label in ['frontend','backend']:
            if label+'_pid' not in data:continue
            env=os.environ.copy();env['M4_UI_PID']=str(data[label+'_pid']);env['M4_UI_EXPECTED']=data['expected_vite' if label=='frontend' else 'expected_jar']
            code="$p=Get-CimInstance Win32_Process -Filter ('ProcessId='+$env:M4_UI_PID); if($p) {if(!$p.CommandLine.Contains($env:M4_UI_EXPECTED)) {throw 'PID owner changed; refusing stop'}; Stop-Process -Id ([int]$env:M4_UI_PID)}"
            subprocess.run([os.environ['M0_PWSH'],'-NoProfile','-Command',code],env=env,check=True)
        print('Owned isolated UI runtime stopped')
