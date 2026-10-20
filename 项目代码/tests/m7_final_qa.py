"""Final current-artifact delivery audit, real runtime and bounded doc links."""
import json,os,py_compile,re,shutil,socket,subprocess,zipfile
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import unquote
from PIL import Image
import m7_support as h
E={'run_at':datetime.now(timezone.utc).isoformat(),'checks':[]};SHA=h.sha(h.JAR)
# The report is itself a local documentation target. Publish an explicit running
# state before link checks, never a speculative passed result.
h.save('M7-final-qa.json',{**E,'result':'running'})
def check(name,ok,detail=None):
    E['checks'].append(dict(name=name,passed=bool(ok),detail=detail));assert ok,name
try:
    for name in ['M7-build.json','M7.2-matrix.json','M7.3-query.json','M7.3-stock.json','M7-main-upgrade.json','M7-replay-after-restart.json','M7-final-release.json','M7-final-closeout.json','M7-final-browser.json','M7-source-diff.json']:
        data=h.load(name);check('passed '+name,data['result']=='passed' and all(c['passed'] for c in data.get('checks',[])))
    check('all T01-T30 individually mapped',len(h.load('M7.2-matrix.json')['scenarios'])==30 and all(x['passed'] and x['proof'] for x in h.load('M7.2-matrix.json')['scenarios']))
    for case,run in h.load('M7.2-matrix.json')['suite_results'].items():
        check('current suite SHA and cleanup '+case,run['artifact_sha256']==SHA and run['all_owned_stopped'])
    for name in ['query','stock']:check('current performance SHA '+name,h.load('M7.3-'+name+'.json')['artifact_sha256']==SHA)
    diff=h.load('M7-source-diff.json');check('actual pinned source patch hash',h.sha(h.OUT/diff['patch'])==diff['patch_sha256'])
    for item in diff['files']:check('current diff source hash '+item['path'],h.sha(h.ROOT/item['path'])==item['current_sha256'])
    notice=h.load('M7-evidence-exception.json');check('historical child evidence exception explicitly disclosed',notice['historical_raw_restored'] is False and h.load(notice['affected_file'])['provenance_warning']['current_result_copy']=='M7.2-returns-binding.json' and h.load('M7.2-returns-binding.json')['database']==notice['current_run_database'])
    release=h.load('M7-final-release.json');close=h.load('M7-final-closeout.json');package=Path(release['package_directory']);manifest=json.loads((package/'manifest.json').read_text(encoding='utf-8-sig'))
    check('main target independent copy and package share final artifact',SHA==h.load('M7-build.json')['backend_sha256']==h.sha(h.ROOT/'.local/backend-run.jar')==release['backend_sha256']==h.sha(package/'app/backend.jar'))
    check('independent test applications closed',release['release_processes_stopped'] and not release['browser_pending'])
    check('manifest hash matches closeout',h.sha(package/'manifest.json')==close['manifest_sha256']==release['manifest_sha256'])
    check('packaged runbook exact current source',h.sha(package/'README.md')==h.sha(h.ROOT/'../学习资料/06-运行交付与证据/独立交付运行手册.md'))
    check('all manifest files exact',all(h.sha(package/x['path'])==x['sha256'] for x in manifest['files']))
    check('archive SHA exact',h.sha(close['archive'])==close['archive_sha256'])
    with zipfile.ZipFile(close['archive']) as archive:check('archive CRC and exact membership',archive.testzip() is None and set(archive.namelist())=={package.name+'/'+x['path'] for x in manifest['files']}|{package.name+'/manifest.json'})
    check('archive no private config data or dependency folder',not any(set(Path(x['path']).parts)&{'data','node_modules','.local','target','config.local.json'} for x in manifest['files']))
    for p in (h.ROOT/'deploy/release').iterdir():
        if p.is_file():check('packaged script exact '+p.name,h.sha(p)==h.sha(package/'bin'/p.name))
    with Image.open(h.OUT/'M7-final-release-browser.jpg') as picture:check('actual JPEG browser proof',picture.size==(1280,900) and picture.format=='JPEG')
    proof=h.load('M7-final-browser.json');check('correct final independent order quantities and messages',proof['order_id']==release['demo']['ids']['bound']['orderId'] and proof['broker_confirmed_count']==5 and all(x in proof['visible_quantity_row'] for x in ['10.000000','4.000000','6.000000','2.000000']))
    # No existing backend/frontend business source changes in M7: V8 is new.
    for x in h.load('M6-changes.json')['files']:
        if x['path'].startswith(('backend/','frontend/src/')):check('preserved M6 business source '+x['path'],h.sha(h.ROOT/x['path'])==x['sha256'])
    baseline=json.loads((h.ROOT/'docs/baseline.lock.json').read_text(encoding='utf-8'));check('fixed lock exact',h.sha(h.ROOT/'docs/baseline.lock.json')==h.sha(package/'baseline.lock.json'))
    for source in baseline['sources']:check('MIT '+source['directory'],h.sha(h.ROOT/source['directory']/'LICENSE')==source['license_sha256']==h.sha(package/'licenses'/(source['directory']+'-MIT.txt')))
    for port in [48081,48082,48083,48084,48085,48086,15174]:check('temporary port free '+str(port),h.free(port))
    for port in [3306,33306,36379,35672,35673,35674,35675,15173,48080]:check('existing service listening '+str(port),not h.free(port))
    client=h.Client(48080).login();check('real authorized runtime',client.api('GET','/fulfillment/job/runtime')['enabled'])
    check('main migrations V0-V8',h.sql('fulfillment','SELECT version FROM ful_flyway_schema_history ORDER BY installed_rank')==tuple((str(n),) for n in range(9)))
    check('main physical inventory remains clean',client.api('POST','/fulfillment/reconcile/run',{'scope':'TENANT'},key='m7-final-qa-'+datetime.now().strftime('%Y%m%d%H%M%S'))['differenceCount']==0)
    docs=['README.md','../学习资料/09-项目规范与进度/PROJECT_STATUS.md','../学习资料/09-项目规范与进度/AI_IMPLEMENTATION_SPEC.md','../学习资料/00-项目总学习手册.md','../学习资料/06-运行交付与证据/独立交付运行手册.md','../学习资料/03-阶段原理讲解/M7-集成性能与交付.md','../学习资料/10-验收证据/M7-验收报告.md','../学习资料/10-验收证据/M7.2-验收报告.md','../学习资料/10-验收证据/M7.3-性能报告.md']+[os.path.relpath(p,h.ROOT).replace(chr(92),"/") for p in (h.ROOT/'../学习资料/04-演示简历与复习').glob('*.md')]+[os.path.relpath(p,h.ROOT).replace(chr(92),"/") for p in (h.ROOT/'../学习资料/05-设计决策与复盘').glob('ADR-01[89]*.md')]
    changed=docs+['scripts/Build-Release.ps1','frontend/.env.release']+[os.path.relpath(p,h.ROOT).replace(chr(92),"/") for p in (h.ROOT/'deploy/release').iterdir() if p.is_file()]+[os.path.relpath(p,h.ROOT).replace(chr(92),"/") for p in (h.ROOT/'tests').glob('m7*') if p.suffix in ['.py','.ps1']]+[os.path.relpath(p,h.ROOT).replace(chr(92),"/") for p in (h.ROOT/'backend/yudao-module-fulfillment/src/main/resources/db/fulfillment').glob('V8__*.sql')]
    for name in sorted(set(changed)):
        path=h.ROOT/name;check('source exists '+name,path.is_file())
        if path.suffix=='.py':py_compile.compile(str(path),doraise=True)
        if path.suffix=='.md':
            for target in re.findall(r'\]\(([^)]+)\)',path.read_text(encoding='utf-8')):
                target=unquote(target.split('#')[0].strip('<>'))
                if target and not re.match(r'[a-z]+:',target,re.I):check('local link '+name+' -> '+target,(path.parent/target).exists())
    h.save('M7-changes.json',{'note':'Explicit file hash inventory, not Git diff; no commits/push/PR. M4.2 historical study packages retained.','count':len(set(changed)),'files':[{'path':n,'sha256':h.sha(h.ROOT/n)} for n in sorted(set(changed))]})
    E.update(backend_sha256=SHA,archive=close['archive'],archive_sha256=close['archive_sha256'],result='passed')
except Exception as error:E.update(result='failed',error=str(error));raise
finally:h.save('M7-final-qa.json',E);print('M7 final QA',E.get('result'),len(E['checks']),flush=True)
