import os
"""Bounded M7.1 delivery evidence audit. No business writes or test reruns."""
import hashlib,json,py_compile,re,shutil,subprocess
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import unquote
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'../学习资料/10-验收证据';E={'run_at':datetime.now(timezone.utc).isoformat(),'checks':[],'scope':'M7.1 only; M7.2-M7.4 not executed'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(name):return json.loads((OUT/name).read_text(encoding='utf-8-sig'))
def save(name,value):(OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
def check(name,ok,detail=None):
    E['checks'].append({'name':name,'passed':bool(ok),'detail':detail})
    if not ok:raise AssertionError(name+': '+str(detail))
save('M7.1-final-qa.json',dict(E,result='running'))
try:
    release=load('M7.1-release.json');close=load('M7.1-closeout.json');package=Path(release['package_directory']);manifest=json.loads((package/'manifest.json').read_text(encoding='utf-8-sig'))
    for name,d in [('release',release),('closeout',close)]:check('passed '+name,d['result']=='passed' and all(c['passed'] for c in d['checks']),len(d['checks']))
    check('temporary apps stopped after browser',release['release_processes_stopped'] and not release['browser_pending'])
    check('package checksum matches tested copy',sha(package/'manifest.json')==release['manifest_sha256']==close['manifest_sha256'])
    check('archive SHA matches actual ZIP',sha(Path(close['archive']))==close['archive_sha256'])
    check('all manifest files match',len(manifest['files'])+1==close['files'] and all(sha(package/x['path'])==x['sha256'] for x in manifest['files']))
    check('same M6 tested backend',release['backend_sha256']==sha(ROOT/'backend/yudao-server/target/yudao-server.jar')==sha(package/'app/backend.jar')==load('M6-build.json')['artifacts']['.local/backend-run.jar'])
    for item in load('M6-changes.json')['files']:
        if item['path'].startswith(('backend/','frontend/src/')):check('preserved existing business code '+item['path'],sha(ROOT/item['path'])==item['sha256'])
    baseline=json.loads((ROOT/'docs/baseline.lock.json').read_text(encoding='utf-8'));check('fixed baseline lock retained',sha(ROOT/'docs/baseline.lock.json')==sha(package/'baseline.lock.json'))
    for s in baseline['sources']:check('original MIT '+s['directory'],sha(ROOT/s['directory']/'LICENSE')==s['license_sha256']==sha(package/'licenses'/(s['directory']+'-MIT.txt')))
    for p in (ROOT/'deploy/release').iterdir():
        if p.is_file():check('tested package script equals source '+p.name,sha(p)==sha(package/'bin'/p.name))
    log=ROOT/'.local'/(package.name+'-frontend-build.log');text=log.read_text(encoding='utf-8',errors='replace')
    check('actual production release build log',bool(re.search(r'building.*release|release.*building',text,re.I)) and 'built in' in text);shutil.copyfile(log,OUT/'M7.1-production-build.log')
    browser=load('M7.1-browser.json');check('real production DOM quantities and messages',browser['result']=='passed' and browser['broker_confirmed_count']==5 and all(x in browser['visible_quantity_row'] for x in ['10.000000','4.000000','6.000000','2.000000']) and browser['order_id']==release['demo']['ids']['bound']['orderId'])
    with Image.open(OUT/'M7.1-release-browser.jpg') as image:check('actual JPEG proof 1280x900',image.format=='JPEG' and image.size==(1280,900))
    runtime=load('M7.1-runtime.json');check('main listeners retained and test ports free',runtime['test_ports_free'] and runtime['main_frontend_status']==200 and {x['LocalPort'] for x in runtime['listeners']}=={3306,15173,33306,36379,48080,35672,35673,35674,35675})
    docs=['README.md','../学习资料/09-项目规范与进度/PROJECT_STATUS.md','../学习资料/09-项目规范与进度/AI_IMPLEMENTATION_SPEC.md','../学习资料/00-项目总学习手册.md','../学习资料/06-运行交付与证据/独立交付运行手册.md','../学习资料/05-设计决策与复盘/ADR-018-M7-交付与性能证据边界.md','../学习资料/03-阶段原理讲解/M7.1-独立交付与固定演示.md','../学习资料/10-验收证据/M7.1-验收报告.md']
    changed=docs+['scripts/Build-Release.ps1','frontend/.env.release']+[os.path.relpath(p,ROOT).replace(chr(92),"/") for p in sorted((ROOT/'deploy/release').iterdir()) if p.is_file()]+[os.path.relpath(p,ROOT).replace(chr(92),"/") for p in sorted((ROOT/'tests').glob('m7_release*')) if p.suffix in ['.py','.ps1']]
    check('unique explicit source list',len(changed)==len(set(changed)));files=[]
    for name in changed:
        p=ROOT/name;check('source exists '+name,p.is_file());files.append({'path':name,'sha256':sha(p)})
        if p.suffix=='.py':py_compile.compile(str(p),doraise=True)
    save('M7.1-changes.json',{'scope':'Explicit M7.1 source inventory, not Git diff. No backend business changes. M7.2-M7.4 remain pending.','files':files,'count':len(files)})
    for name in docs:
        p=ROOT/name;t=p.read_text(encoding='utf-8');check('UTF8 fences '+name,'\ufffd' not in t and not t.startswith('\ufeff') and len(re.findall(r'^```',t,re.M))%2==0)
        for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)',t):
            target=unquote(target.strip('<>').split('#')[0])
            if target and not re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:',target):check('link '+name+' -> '+target,(p.parent/target).exists())
    for name in ['serve.cjs','Seed-Demo.cjs']:
        r=subprocess.run([shutil.which('node'),'--check',str(ROOT/'deploy/release'/name)],capture_output=True,text=True,timeout=15);check('Node syntax '+name,r.returncode==0)
    E.update(source_count=len(files),result='passed')
except Exception as error:E.update(result='failed',error=str(error));raise
finally:save('M7.1-final-qa.json',E);print('M7.1 QA',E.get('result'),len(E['checks']),'checks',flush=True)
