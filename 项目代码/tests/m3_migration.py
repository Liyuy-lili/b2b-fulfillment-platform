"""One-time V2 -> V3 migration with stock preservation and immutable migration checks."""
import hashlib,json,os,subprocess
from datetime import datetime,timezone
from m1_acceptance import ROOT,sql

def main():
    e={'run_at':datetime.now(timezone.utc).isoformat(),'checks':[],'commands':[]}
    def check(name,ok,detail=None):
        e['checks'].append({'name':name,'passed':bool(ok),'detail':detail})
        if not ok:raise AssertionError(name)
    def command(script,*args):
        out=ROOT/'.local'/('m3-'+Path(script).name+'-out.log');err=out.with_name(out.stem+'-err.log')
        with out.open('w',encoding='utf-8') as stdout,err.open('w',encoding='utf-8') as stderr:
            result=subprocess.run([os.environ.get('M0_PWSH','pwsh'),'-NoProfile','-File',str(ROOT/script),*args],cwd=ROOT,stdout=stdout,stderr=stderr,timeout=120)
        output=out.read_text(encoding='utf-8',errors='replace');error=err.read_text(encoding='utf-8',errors='replace')
        e['commands'].append({'script':script,'args':args,'exit':result.returncode,'output':output,'error':error})
        if result.returncode:raise AssertionError(script+output+error)
    def stock():return [[str(v) for v in row] for row in sql('SELECT tenant_id,product_id,warehouse_id,`count`,ful_reserved_count FROM erp_stock ORDER BY id')]
    try:
        check('main database is V2 before upgrade',str(sql('SELECT MAX(CAST(version AS UNSIGNED)) FROM ful_flyway_schema_history')[0][0])=='2')
        manifest=json.loads((ROOT/'../学习资料/10-验收证据/M2-changes.json').read_text(encoding='utf-8'))
        for version in ['V1__','V2__']:
            file=next(f for f in manifest['files'] if '/'+version in f['path'])
            check('immutable '+version,hashlib.sha256((ROOT/file['path']).read_bytes()).hexdigest()==file['sha256'])
        before=stock();command('scripts/Stop-Local.ps1')
        command('scripts/Migrate-Database.ps1','-Action','migrate');command('scripts/Migrate-Database.ps1','-Action','validate')
        check('V3 recorded successfully',sql("SELECT success FROM ful_flyway_schema_history WHERE version='3'")[0][0]==1)
        check('all H R stock facts preserved',stock()==before,len(before))
        check('new cancellation facts table starts empty',sql('SELECT COUNT(*) FROM ful_cancellation')[0][0]==0)
        command('scripts/Start-Local.ps1');e['result']='passed'
    finally:
        (ROOT/'../学习资料/10-验收证据/M3-migration.json').write_text(json.dumps(e,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
if __name__=='__main__':main()
