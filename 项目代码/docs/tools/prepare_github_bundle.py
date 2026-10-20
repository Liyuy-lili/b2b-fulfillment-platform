"""Build a reviewable source/study bundle without changing runtime source files."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,re,shutil,subprocess,zipfile,sys

ROOT=Path(__file__).resolve().parents[3]
CODE=ROOT/'项目代码'
OUT=CODE/'.local/github-publish'
PATTERNS={
 'github-token':re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b'),
 'cloud-access-key':re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
 'jwt':re.compile(r'\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b'),
 'private-key':re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
}
def sha(data):return hashlib.sha256(data).hexdigest()
def inventory():
    raw=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=ROOT)
    files={ROOT/p.decode('utf-8') for p in raw.split(b'\0') if p}
    # Evidence logs are curated learning sources, unlike disposable runtime logs.
    files.update((ROOT/'学习资料/10-验收证据').glob('*.log'))
    return sorted(p for p in files if p.is_file())
def main():
    files=inventory();rows=[];findings=[];oversize=[]
    for p in files:
        name=p.relative_to(ROOT).as_posix();data=p.read_bytes()
        if len(data)>95*1024**2:oversize.append(name)
        if b'\0' not in data and len(data)<12*1024**2:
            try:text=data.decode('utf-8-sig')
            except UnicodeDecodeError:text=''
            for kind,pattern in PATTERNS.items():
                n=len(pattern.findall(text))
                if n:findings.append({'path':name,'kind':kind,'occurrences':n})
        rows.append({'path':name,'bytes':len(data),'sha256':sha(data)})
    OUT.mkdir(parents=True,exist_ok=True)
    report={'run_at':datetime.now(timezone.utc).isoformat(),'files':len(rows),'source_bytes':sum(x['bytes'] for x in rows),'free_bytes':shutil.disk_usage(OUT).free,'secret_candidates':findings,'oversize':oversize,'sources':rows,'scope':'Git-eligible source and learning materials, plus curated evidence logs. Excludes local dependencies, databases, runtime files, generated builds and active personal config.'}
    (OUT/'preflight.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({k:report[k] for k in ['files','source_bytes','free_bytes','secret_candidates','oversize']},ensure_ascii=False),flush=True)
    if '--build' not in sys.argv:return
    # The nine unchanged upstream IoT tests contain public, synthetic JWT fixtures.
    # Anything outside those known source fixtures blocks publication for inspection.
    unexpected=[x for x in findings if not (x['kind']=='jwt' and '/yudao-module-iot/' in x['path'] and '/src/test/' in x['path'])]
    if unexpected or oversize:raise SystemExit('Review secret candidates or oversized files before publication.')
    needed=report['source_bytes']*3
    if report['free_bytes']<needed:raise SystemExit('Insufficient free disk for staging and ZIP verification.')
    stamp=datetime.now().strftime('%Y%m%d-%H%M%S')
    stage=OUT/('stage-'+stamp)/'b2b-fulfillment-platform'
    if stage.exists():raise SystemExit('Unique staging directory required; never overwrite.')
    stage.mkdir(parents=True)
    # Staging adds a directory level; use the Windows extended path form for long upstream names.
    if os.name=='nt':stage=Path('\\\\?\\'+str(stage.resolve()))
    for row in rows:
        src=ROOT/row['path'];dst=stage/row['path']
        dst.parent.mkdir(parents=True,exist_ok=True)
        copy_src='\\\\?\\'+str(src.resolve()) if os.name=='nt' else str(src)
        shutil.copy2(copy_src,str(dst))
        if sha(dst.read_bytes())!=row['sha256']:raise ValueError('Staged hash mismatch '+row['path'])
    package_manifest={'created_at':report['run_at'],'scope':report['scope'],'files':rows,'upstream_public_test_fixture_matches':findings,'excluded':'node_modules, target, dist, .local, runtime data, active personal configuration; no production business data included','not_rerun':'Business tests, DB migrations and performance tests were not rerun while packaging.'}
    (stage/'SOURCE_MANIFEST.json').write_text(json.dumps(package_manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    archive=CODE/'.local/releases'/('b2b-fulfillment-source-'+stamp+'.zip');archive.parent.mkdir(parents=True,exist_ok=True)
    members=rows+[{'path':'SOURCE_MANIFEST.json','bytes':(stage/'SOURCE_MANIFEST.json').stat().st_size,'sha256':sha((stage/'SOURCE_MANIFEST.json').read_bytes())}]
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for row in members:z.write(stage/row['path'],'b2b-fulfillment-platform/'+row['path'])
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:raise ValueError('ZIP CRC mismatch')
        expected={'b2b-fulfillment-platform/'+row['path'] for row in members}
        if set(z.namelist())!=expected:raise ValueError('ZIP membership mismatch')
        for row in members:
            if sha(z.read('b2b-fulfillment-platform/'+row['path']))!=row['sha256']:raise ValueError('ZIP source hash mismatch '+row['path'])
    result={'result':'passed','archive':str(archive),'archive_bytes':archive.stat().st_size,'archive_sha256':sha(archive.read_bytes()),'stage':str(stage),'source_files':len(rows),'zip_entries':len(members),'verified':'CRC, exact membership, every staged source SHA256 and every ZIP entry SHA256','scope':report['scope'],'business_tests_rerun':False}
    (OUT/'bundle.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(result,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
