"""Run once to upgrade the M1 main/clean DBs and probe a separate, disposable dirty M0 fixture.
The dirty fixture is deliberately retained; no automatic business data repair/reset.
"""
import json,os,subprocess
from pathlib import Path
from datetime import datetime,timezone
import pymysql

ROOT=Path(__file__).resolve().parents[1]
DIRTY='fulfillment_m2_dirty_20261018'
E={'date':'2026-10-18','run_at':datetime.now(timezone.utc).isoformat(),'checks':[],'commands':[]}
def check(name,ok,detail=None):
    E['checks'].append({'name':name,'passed':bool(ok),'detail':detail})
    if not ok:raise AssertionError(name+': '+str(detail))
def db(name):return pymysql.connect(host='127.0.0.1',port=33306,user='fulfillment',password='fulfillment-dev',database=name,autocommit=True)
def invoke(name,action,expected=True):
    result=subprocess.run(['java','-Dloader.main=cn.iocoder.yudao.module.fulfillment.framework.FulfillmentMigrationTool','-cp',str(ROOT/'backend/yudao-server/target/yudao-server.jar'),'org.springframework.boot.loader.launch.PropertiesLauncher',action],env=os.environ|{'DB_NAME':name},stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=90)
    output=result.stdout.decode('utf-8',errors='replace');E['commands'].append({'db':name,'action':action,'exit':result.returncode,'output':output})
    check(name+' '+action+' expected result',(result.returncode==0)==expected,result.returncode)
    return output
def main():
    invoke(DIRTY,'baseline')
    with db(DIRTY) as c:
        with c.cursor() as cur:
            cur.execute('INSERT INTO erp_stock (product_id,warehouse_id,tenant_id,`count`) VALUES (991,991,1,-1)')
            ident=cur.lastrowid
        check('negative fixture reported','invalid stock id='+str(ident) in invoke(DIRTY,'migrate',False))
        with c.cursor() as cur:
            cur.execute('UPDATE erp_stock SET `count`=0,deleted=1 WHERE id=%s',(ident,))
        check('deleted fixture reported','STOCK_PREFLIGHT_REFUSED' in invoke(DIRTY,'migrate',False))
        with c.cursor() as cur:
            cur.execute('UPDATE erp_stock SET deleted=0 WHERE id=%s',(ident,))
            cur.execute('ALTER TABLE erp_stock DROP INDEX uk_stock_identity')
            cur.execute('INSERT INTO erp_stock (product_id,warehouse_id,tenant_id,`count`) VALUES (991,991,1,0)')
        check('duplicates reported with identity','duplicate tenant=1,product=991,warehouse=991' in invoke(DIRTY,'migrate',False))
        with c.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='erp_stock' AND COLUMN_NAME='ful_reserved_count'")
            check('dirty migrations do not alter stock schema',cur.fetchone()[0]==0)
            cur.execute('SELECT COUNT(*) FROM erp_stock');check('dirty fixture rows retained',cur.fetchone()[0]==2)
    for name in ['fulfillment','fulfillment_m1_clean_20261017']:
        with db(name) as c:
            with c.cursor() as cur:
                cur.execute('SELECT id,tenant_id,product_id,warehouse_id,`count` FROM erp_stock ORDER BY id');before=cur.fetchall()
            invoke(name,'migrate');invoke(name,'validate')
            with c.cursor() as cur:
                cur.execute('SELECT id,tenant_id,product_id,warehouse_id,`count` FROM erp_stock ORDER BY id');check(name+' physical facts preserved',before==cur.fetchall())
                cur.execute('SELECT COUNT(*) FROM erp_stock WHERE ful_reserved_count<>0');check(name+' initial reserved zero',cur.fetchone()[0]==0)
                cur.execute('SELECT version FROM ful_flyway_schema_history ORDER BY installed_rank');check(name+' versions 0 1 2',cur.fetchall()==(('0',),('1',),('2',)))
    E['result']='passed'
if __name__=='__main__':
    try:main()
    except Exception as exc:E['result']='failed';E['error']=str(exc);raise
    finally:
        (ROOT/'../学习资料/10-验收证据/M2-migration.json').write_text(json.dumps(E,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
        print('M2 migration',E.get('result'),len(E['checks']),'checks')
