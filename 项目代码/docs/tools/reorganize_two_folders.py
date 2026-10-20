"""One-time, archived two-folder migration. Run without --apply to inspect the plan."""
from pathlib import Path
import hashlib,json,os,re,sys,zipfile
from datetime import datetime,timezone
from urllib.parse import unquote,urlsplit

ROOT=Path(__file__).resolve().parents[2]
if ROOT.name=='项目代码':ROOT=ROOT.parent
CODE=ROOT/'项目代码';PACK=ROOT/'学习资料';OLD=ROOT/'项目学习资料'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def safe(p):
    p=p.resolve()
    if not p.is_relative_to(ROOT) or p==ROOT:raise ValueError('Outside workspace: '+str(p))
    return p
def relative(p):return os.path.relpath(p,ROOT).replace('\\','/')
def write(p,t):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(t,encoding='utf-8',newline='\n')
def main():
    if CODE.exists() or PACK.exists():raise SystemExit('Already moved or destination exists; refusing to repeat.')
    prefixes={ROOT/n:CODE/n for n in ['backend','frontend','deploy','scripts','tests','.local']}
    prefixes.update({OLD:PACK,ROOT/'docs/evidence':PACK/'10-验收证据',ROOT/'docs/decisions':PACK/'05-设计决策与复盘',ROOT/'docs/tools':CODE/'docs/tools'})
    files={ROOT/'README.md':CODE/'README.md',ROOT/'docs/baseline.lock.json':CODE/'docs/baseline.lock.json'}
    for name in ['AI_IMPLEMENTATION_SPEC.md','PROJECT_STATUS.md']:
        files[ROOT/'docs'/name]=PACK/'09-项目规范与进度'/name
    files[ROOT/'docs/RELEASE_RUNBOOK.md']=PACK/'06-运行交付与证据/独立交付运行手册.md'
    aliases={ROOT/'docs/LEARNING_AND_INTERVIEW_GUIDE.md':OLD/'00-项目总学习手册.md'}
    stubs=[]
    for folder in ['学习资料','面试问答','lessons','final']:
        for p in (ROOT/'docs'/folder).glob('*'):
            if not p.is_file():raise ValueError('Unexpected nested item '+str(p))
            if p.suffix=='.md':
                t=p.read_text(encoding='utf-8-sig')
                if not t.startswith('# 资料已集中整理'):raise ValueError('Unique content, do not delete: '+str(p))
                m=re.search(r'\]\(([^)]+)\)',t);q=(p.parent/unquote(m[1].split('#')[0])).resolve()
                if not q.is_file():raise ValueError('Missing retained document '+str(q))
                aliases[p]=q;stubs.append(p)
            elif p.name=='资料快照.json':
                # Provenance from an older generation, retained inside the recovery ZIP.
                aliases[p]=OLD/'01-系统学习教程/资料快照.json';stubs.append(p)
            else:raise ValueError('Unrecognized file, refusing delete: '+str(p))
    def dest(p):
        p=p.resolve()
        if p in aliases:return dest(aliases[p])
        if p in files:return files[p]
        for src,dst in sorted(prefixes.items(),key=lambda x:len(str(x[0])),reverse=True):
            if p==src or p.is_relative_to(src):return dst/p.relative_to(src)
        if p==ROOT/'docs':return CODE/'docs'
        return p
    def rebase(t,old,new):
        def sub(m):
            value=m[2].strip('<>')
            if urlsplit(value).scheme or value.startswith(('#','//')):return m[0]
            name,sep,frag=unquote(value).partition('#');target=dest(old.parent/name)
            return m[1]+os.path.relpath(target,new.parent).replace('\\','/')+(sep+frag if sep else '')+m[3]
        return re.sub(r'(!?\[[^\]\n]*\]\()([^\n)]+)(\))',sub,t)
    duplicates=[]
    for p in (ROOT/'docs/decisions').glob('*.md'):
        q=OLD/'05-设计决策与复盘'/p.name
        duplicates.append((p,q))
    duplicates.append((ROOT/'docs/RELEASE_RUNBOOK.md',OLD/'06-运行交付与证据/独立交付运行手册.md'))
    def content(p):
        t=re.sub(r'^> 阅读语境：[^\n]*\n','',p.read_text(encoding='utf-8-sig'),flags=re.M)
        t=rebase(t,p,dest(p));return re.sub(r'\n\s*\n','\n\n',t).strip()
    for p,q in duplicates:
        if content(p)!=content(q):raise ValueError('Copies have unique differences; refusing deletion: '+str(p))
    # All project-authored documents, scripts and tests are recoverable before any mutation.
    originals=set((ROOT/'docs').rglob('*'))|set(OLD.rglob('*'))|set((ROOT/'scripts').rglob('*'))|set((ROOT/'tests').rglob('*'))|{ROOT/'README.md',ROOT/'AGENTS.md',ROOT/'.gitignore'}
    originals={p for p in originals if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.zip'}
    md={p:p.read_text(encoding='utf-8-sig') for p in originals if p.suffix=='.md'}
    preserved={relative(p):sha(p) for p in originals}
    core=json.loads((ROOT/'docs/evidence/M7-source-diff.json').read_text(encoding='utf-8'))
    for e in core['files']:
        p=ROOT/e['path']
        if sha(p)!=e['current_sha256']:raise ValueError('Existing business source drift: '+e['path'])
        preserved[relative(p)]=sha(p)
    for p in (ROOT/'backend/yudao-module-fulfillment/src/main/resources/db/fulfillment').glob('V*.sql'):preserved[relative(p)]=sha(p)
    for p in [ROOT/'backend/LICENSE',ROOT/'frontend/LICENSE',ROOT/'backend/yudao-server/target/yudao-server.jar',ROOT/'.local/backend-run.jar']:
        if p.exists():preserved[relative(p)]=sha(p)
    print(json.dumps({'confirmed_duplicate_copies':len(duplicates),'obsolete_stubs_and_snapshot':len(stubs)+1,'archived_documents_and_scripts':len(originals),'two_main_folders':['项目代码','学习资料']},ensure_ascii=False),flush=True)
    if '--apply' not in sys.argv:return
    archive=ROOT/'.local/20261020-两文件夹整理前备份.zip'
    if archive.exists():raise ValueError('Backup already exists')
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(originals):z.write(p,relative(p))
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None or any(hashlib.sha256(z.read(n)).hexdigest()!=h for n,h in preserved.items() if ROOT/n in originals):raise ValueError('Backup verification failed')
    archive_sha=sha(archive)
    CODE.mkdir();safe(OLD).rename(safe(PACK))
    for name in ['backend','frontend','deploy','scripts','tests','.local']:safe(ROOT/name).rename(safe(CODE/name))
    # Engineering documents join the learning collection; executable doc tools remain with code.
    (CODE/'docs').mkdir()
    for name in ['evidence','tools']:
        safe(ROOT/'docs'/name).rename(safe(dest(ROOT/'docs'/name)))
    for p,q in files.items():
        if p==ROOT/'docs/RELEASE_RUNBOOK.md':continue
        q.parent.mkdir(parents=True,exist_ok=True);safe(p).rename(safe(q))
    removed=[]
    for p,q in duplicates:
        safe(p).unlink();removed.append({'old':relative(p),'retained':relative(dest(q)),'reason':'same-content-after-link-rebase-and-reading-context','sha256_before':preserved[relative(p)]})
    for p in stubs+[ROOT/'docs/LEARNING_AND_INTERVIEW_GUIDE.md']:
        safe(p).unlink();removed.append({'old':relative(p),'retained':relative(dest(p)),'reason':'obsolete-redirect-or-snapshot','sha256_before':preserved[relative(p)]})
    for p in sorted((ROOT/'docs').rglob('*'),key=lambda p:len(p.parts),reverse=True):
        if p.is_dir():safe(p).rmdir()
    safe(ROOT/'docs').rmdir()
    deleted={e['old'] for e in removed}
    edited=[]
    for p,t in md.items():
        if relative(p) in deleted:continue
        q=dest(p);new=rebase(t,p,q)
        if new!=t:write(q,new);edited.append(relative(q))
    replacements={
        'docs/LEARNING_AND_INTERVIEW_GUIDE.md':'../学习资料/00-项目总学习手册.md',
        'docs/AI_IMPLEMENTATION_SPEC.md':'../学习资料/09-项目规范与进度/AI_IMPLEMENTATION_SPEC.md',
        'docs/PROJECT_STATUS.md':'../学习资料/09-项目规范与进度/PROJECT_STATUS.md',
        'docs/RELEASE_RUNBOOK.md':'../学习资料/06-运行交付与证据/独立交付运行手册.md',
        'docs/evidence':'../学习资料/10-验收证据',
        'docs/decisions':'../学习资料/05-设计决策与复盘',
        'docs/lessons':'../学习资料/03-阶段原理讲解',
        'docs/final':'../学习资料/04-演示简历与复习',
        'docs/学习资料':'../学习资料/01-系统学习教程',
        'docs/面试问答':'../学习资料/02-面试问答',
        '项目学习资料/':'../学习资料/',
    }
    for directory in [CODE/'scripts',CODE/'tests']:
        for p in directory.rglob('*'):
            if p.suffix not in {'.py','.ps1','.cjs'}:continue
            t=p.read_text(encoding='utf-8-sig');new=t
            for a,b in replacements.items():new=new.replace(a,b)
            # A document may now be outside the code directory; recorded paths remain portable.
            new=re.sub(r'(\w+)\.relative_to\((h\.)?ROOT\)\.as_posix\(\)',lambda m:'os.path.relpath('+m[1]+','+(m[2] or '')+'ROOT).replace(chr(92),"/")',new) if 'relative_to(' in new and 'docs/' in t else new
            if new!=t:
                if 'os.path.relpath' in new and not re.search(r'^import .*\bos\b',new,re.M):new='import os\n'+new
                write(p,new);edited.append(relative(p))
    # The old one-time tool must never recreate redirect files after this cleanup.
    oldtool=CODE/'docs/tools/organize_learning_materials.py'
    write(oldtool,'"""Obsolete migration entry. Original source is in the recovery archive."""\nraise SystemExit("资料已整理为项目代码和学习资料；不要重新创建旧路径。")\n')
    write(ROOT/'.gitignore',(ROOT/'.gitignore').read_text(encoding='utf-8').replace('.local/','项目代码/.local/').replace('!frontend/.env','!项目代码/frontend/.env').replace('deploy/.env','项目代码/deploy/.env'))
    a=(ROOT/'AGENTS.md').read_text(encoding='utf-8').replace('`docs/AI_IMPLEMENTATION_SPEC.md`','`学习资料/09-项目规范与进度/AI_IMPLEMENTATION_SPEC.md`').replace('`docs/PROJECT_STATUS.md`','`学习资料/09-项目规范与进度/PROJECT_STATUS.md`').replace('`docs/LEARNING_AND_INTERVIEW_GUIDE.md`','`学习资料/00-项目总学习手册.md`')
    a+='\n11. 项目根目录只保留“项目代码”和“学习资料”两个主文件夹；隐藏 .git 与根 AGENTS.md/.gitignore 是仓库配置。代码命令从“项目代码”运行，学习资料只保留一份，历史路径查整理清单。\n'
    write(ROOT/'AGENTS.md',a)
    entries=[{'old':n,'new':relative(dest(ROOT/n)),'sha256_before':h,'deleted':n in deleted} for n,h in preserved.items()]
    manifest={'date':datetime.now(timezone.utc).isoformat(),'root':str(ROOT),'folders':['项目代码','学习资料'],'archive':'项目代码/.local/'+archive.name,'archive_sha256':archive_sha,'removed':removed,'files':entries,'link_or_script_path_updates':edited,'prefixes':{relative(p):relative(q) for p,q in prefixes.items()},'aliases':{relative(p):relative(dest(q)) for p,q in aliases.items()},'note':'Recovery archive contains pre-move authored docs/scripts/tests; source, runtime and dependency directories renamed as units. Raw stage JSON/XML/CSV/logs and business source are immutable. Markdown links and executable script paths may change; no business tests executed.'}
    write(PACK/'整理清单.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print('MOVED; follow-up tools and navigation updates required.',flush=True)

if __name__=='__main__':main()
