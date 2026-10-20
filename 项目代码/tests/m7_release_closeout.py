"""Close M7.1 after browser proof: stop owned apps, archive clean package.
Only manifest-listed distribution files enter ZIP; no active config/data.
"""
import hashlib,json,os,shutil,socket,subprocess,time,zipfile
from datetime import datetime,timezone
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'../学习资料/10-验收证据'
PREFIX=os.getenv('M7_DELIVERY_PREFIX','M7.1');assert PREFIX in ['M7.1','M7-final']
source=json.loads((OUT/(PREFIX+'-release.json')).read_text(encoding='utf-8'));clean=Path(source['release_directory']);package=Path(source['package_directory'])
E={'run_at':datetime.now(timezone.utc).isoformat(),'checks':[]}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def check(name,ok,detail=None):
    E['checks'].append({'name':name,'passed':bool(ok),'detail':detail})
    if not ok:raise AssertionError(name+': '+str(detail))
def free(port):
    with socket.socket() as s:return s.connect_ex(('127.0.0.1',port))!=0
try:
    check('release scenario passed before closeout',source['result']=='passed' and all(x['passed'] for x in source['checks']))
    proof=json.loads((OUT/(PREFIX+'-browser.json')).read_text(encoding='utf-8'));check('production browser proof uses isolated port and correct order',proof['result']=='passed' and proof['url'].startswith('http://127.0.0.1:15174/') and proof['order_id']==source['demo']['ids']['bound']['orderId'])
    with Image.open(OUT/(PREFIX+'-release-browser.jpg')) as picture:check('actual desktop JPEG proof',picture.format=='JPEG' and picture.size==(1280,900))
    log=ROOT/'.local/m7-release-close-stop.log'
    with log.open('wb') as out:r=subprocess.run([os.getenv('M0_PWSH','pwsh'),'-NoProfile','-File',str(clean/'bin/Stop-Release.ps1')],cwd=clean,stdout=out,stderr=subprocess.STDOUT,timeout=45)
    check('owned release stop exits0',r.returncode==0)
    until=time.monotonic()+25
    while time.monotonic()<until and not(free(48082) and free(15174)):time.sleep(.25)
    check('isolated frontend and backend ports free',free(48082) and free(15174))
    check('original main services still listening',not free(48080) and not free(15173) and not free(33306) and not free(36379) and not free(35672))
    manifest=json.loads((package/'manifest.json').read_text(encoding='utf-8-sig'));files=[x['path'] for x in manifest['files']]+['manifest.json']
    check('manifest files unchanged before archive',all(sha(package/x['path'])==x['sha256'] for x in manifest['files']))
    total=sum((package/f).stat().st_size for f in files);check('archive preflight free space',shutil.disk_usage(package).free>total*2,{'file_count':len(files),'input_bytes':total})
    archive=package.parent/(package.name+'.zip');check('archive output new and outside input directory',not archive.exists() and not archive.resolve().is_relative_to(package.resolve()))
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
        for f in files:z.write(package/f,arcname=package.name+'/'+f)
    with zipfile.ZipFile(archive) as z:check('ZIP CRC and exact manifest membership',z.testzip() is None and set(z.namelist())=={package.name+'/'+f for f in files})
    check('ZIP excludes active config private files and dependency folders',not any(set(Path(f).parts)&{'node_modules','data','config.local.json'} for f in files))
    for name,suffix in [('demo.json','-demo.json'),('demo-import.csv','-demo.csv'),('demo-error.csv','-errors.csv'),('demo-stock.xlsx','-stock.xlsx')]:shutil.copyfile(clean/'data'/name,OUT/(PREFIX+suffix))
    for p in (ROOT/'.local').glob('m7-release-*.log'):shutil.copyfile(p,OUT/(PREFIX+'-'+p.name))
    for p in (clean/'data/logs').glob('*.log'):shutil.copyfile(p,OUT/(PREFIX+'-clean-'+p.name))
    source.update(browser_pending=False,release_processes_stopped=True,closed_at=datetime.now(timezone.utc).isoformat());(OUT/(PREFIX+'-release.json')).write_text(json.dumps(source,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    E.update(archive=str(archive),archive_sha256=sha(archive),archive_bytes=archive.stat().st_size,manifest_sha256=sha(package/'manifest.json'),files=len(files),result='passed')
except Exception as error:E.update(result='failed',error=str(error));raise
finally:
    (OUT/(PREFIX+'-closeout.json')).write_text(json.dumps(E,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(PREFIX+' closeout',E.get('result'),len(E['checks']),'checks',flush=True)
