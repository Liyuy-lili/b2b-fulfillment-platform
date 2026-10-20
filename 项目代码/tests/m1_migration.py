"""Real Flyway adoption on the existing M0 DB and an independently initialized M0 DB.
Run after Initialize-Database -Database fulfillment_m1_clean_20261017, with application writes paused.
Never drops/resets a database. Negative probes modify only dedicated test metadata/schema.
"""
import json,os,subprocess,sys
from pathlib import Path
from datetime import datetime,timezone
import pymysql

ROOT=Path(__file__).resolve().parents[1]
E={'run_at':datetime.now(timezone.utc).isoformat(),'checks':[],'commands':[]}
CLEAN=os.getenv('M1_CLEAN_DB','fulfillment_m1_clean_20261017')

def connect(db):
    return pymysql.connect(host='127.0.0.1',port=33306,user='fulfillment',password='fulfillment-dev',database=db,autocommit=True)
def check(name,ok,detail=None):
    E['checks'].append({'name':name,'passed':bool(ok),'detail':detail})
    if not ok:raise AssertionError(name+': '+str(detail))
def invoke(db,action,ok=True,contains=None):
    env=os.environ|{'DB_NAME':db}
    result=subprocess.run(['java','-Dloader.main=cn.iocoder.yudao.module.fulfillment.framework.FulfillmentMigrationTool','-cp',str(ROOT/'backend/yudao-server/target/yudao-server.jar'),'org.springframework.boot.loader.launch.PropertiesLauncher',action],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=90)
    out=result.stdout.decode('utf-8',errors='replace')
    E['commands'].append({'database':db,'action':action,'exit':result.returncode,'output':out})
    check(f'{db} {action} expected result',(result.returncode==0)==ok and (contains is None or contains in out),result.returncode)
def snapshot(c):
    manifest=json.loads((ROOT/'backend/yudao-module-fulfillment/src/main/resources/m0-baseline.json').read_text())
    result={}
    with c.cursor() as cur:
        for table in manifest:
            cur.execute('SELECT COUNT(*) FROM `'+table+'`');result[table]=cur.fetchone()[0]
    return result

def main():
    # Do not run a destructive probe against the main DB.
    assert CLEAN.startswith('fulfillment_m1_clean_') and CLEAN!='fulfillment'
    with connect(CLEAN) as clean:
        with clean.cursor() as cur:
            cur.execute('ALTER TABLE erp_product ADD COLUMN m1_guard_probe INT NULL')
        invoke(CLEAN,'baseline',False,'columns mismatch')
        with clean.cursor() as cur:cur.execute('ALTER TABLE erp_product DROP COLUMN m1_guard_probe')
    for db in ['fulfillment',CLEAN]:
        with connect(db) as c:
            before=snapshot(c)
            invoke(db,'migrate',False,'non-empty schema')
            invoke(db,'baseline')
            invoke(db,'migrate')
            invoke(db,'validate')
            invoke(db,'migrate')
            after=snapshot(c)
            # V1 adds precisely two menu records; all other M0 row counts remain unchanged.
            check(db+' preserves existing rows',all(after[t]==n+(2 if t=='system_menu' else 0) for t,n in before.items()),{'before':before,'after':after})
            with c.cursor() as cur:
                cur.execute("SELECT version,success FROM ful_flyway_schema_history ORDER BY installed_rank")
                check(db+' history 0 then 1',cur.fetchall()==(('0',1),('1',1)))
                cur.execute("SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME LIKE 'ful\\_%' AND TABLE_NAME<>'ful_flyway_schema_history'")
                check(db+' nine P0 tables',cur.fetchone()[0]==9)
            invoke(db,'baseline',False,'table set mismatch')
    with connect(CLEAN) as c:
        with c.cursor() as cur:
            cur.execute("SELECT checksum FROM ful_flyway_schema_history WHERE version='1'");original=cur.fetchone()[0]
            cur.execute("UPDATE ful_flyway_schema_history SET checksum=checksum+1 WHERE version='1'")
        try:invoke(CLEAN,'validate',False,'checksum mismatch')
        finally:
            with c.cursor() as cur:cur.execute("UPDATE ful_flyway_schema_history SET checksum=%s WHERE version='1'",(original,))
        invoke(CLEAN,'validate')

if __name__=='__main__':
    try:main();E['result']='passed'
    except Exception as exc:E['result']='failed';E['error']=str(exc);raise
    finally:
        (ROOT/'../学习资料/10-验收证据/M1-migration.json').write_text(json.dumps(E,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(E.get('result'),len(E['checks']),'migration checks')
