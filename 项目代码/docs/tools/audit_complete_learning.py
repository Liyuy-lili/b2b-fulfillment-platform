"""Static audit of the consolidated M7 learning pack. Never executes application tests."""
from __future__ import annotations
from project_layout import PACK, EVIDENCE, WORKSPACE, legacy
import hashlib,json,os,re,zipfile
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import unquote,urlsplit
from xml.etree import ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]

STUDY=PACK/'01-系统学习教程'
QA=PACK/'02-面试问答'
INDEX=PACK/'07-证据与源码索引'


def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def clean(text):return re.sub(r'^```[^\n]*\n.*?^```\s*$','',text,flags=re.M|re.S)
def anchor_set(text):
    result=set(re.findall(r'<a\s+id="([^"]+)"',text));counts={}
    for title in re.findall(r'^#{1,6}\s+(.+)$',clean(text),re.M):
        slug=re.sub(r'[^\w\-\s\u4e00-\u9fff]','',title.replace('`','').lower()).replace(' ','-')
        n=counts.get(slug,0);counts[slug]=n+1;result.add(slug+(f'-{n}' if n else ''))
    return result
def portable(p,base=INDEX):return os.path.relpath(p,base).replace('\\','/')
def write(p,text):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text.rstrip()+'\n',encoding='utf-8',newline='\n')

def inventory():
    diff=json.loads((EVIDENCE/'M7-source-diff.json').read_text(encoding='utf-8'))
    files={legacy(e['path']) for e in diff['files']}
    for folder in ['backend/yudao-module-fulfillment/src','tests','scripts','deploy']:
        for directory,dirs,names in os.walk(ROOT/folder):
            dirs[:]=[d for d in dirs if d not in {'target','node_modules','__pycache__','.git','dist'}]
            for name in names:
                p=Path(directory)/name
                if p.suffix in {'.java','.sql','.xml','.yaml','.yml','.ts','.vue','.py','.ps1','.cjs','.json','.md','.txt'}:files.add(p)
    # Read all nonbinary evidence metadata; logs/binaries remain linked original evidence.
    files.update(EVIDENCE.glob('M*.json'));files.update(EVIDENCE.glob('M*.md'));files.update(EVIDENCE.glob('M7-junit-*.xml'))
    files.update([legacy('docs/AI_IMPLEMENTATION_SPEC.md'),legacy('docs/PROJECT_STATUS.md'),ROOT/'docs/baseline.lock.json'])
    rows=[]
    for p in sorted(files):
        if not p.exists():continue
        raw=p.read_bytes();text=raw.decode('utf-8-sig',errors='replace')
        symbols=[]
        for n,line in enumerate(text.splitlines(),1):
            match=re.search(r'\b(?:class|interface|record|enum)\s+(\w+)',line) if p.suffix=='.java' else re.match(r'(?:async\s+)?def\s+(\w+)\(',line) if p.suffix=='.py' else None
            if match:symbols.append({'name':match.group(1),'line':n})
        rows.append({'path':os.path.relpath(p,ROOT).replace(chr(92),'/'),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'lines':len(text.splitlines()),'symbols':symbols})
    snapshot={'as_of':'2026-10-20','scope':'Read/inventory project-owned fulfillment and upstream-diff sources, tests/deploy/scripts/ADRs/evidence; not a claim of line-by-line review of all untouched upstream modules or a test rerun.','files':rows}
    write(INDEX/'项目审阅快照.json',json.dumps(snapshot,ensure_ascii=False,indent=2))
    counts=Counter(x['path'].split('/')[0] for x in rows)
    out=['# 当前项目文件与源码清单','','2026-10-20静态读取与来源记录。该清单不等于重新编译/运行，也不声称逐行复读所有未修改上游模块。重点语义阅读为核心履约/核对/消息/任务/权限/性能/交付链。','','## 目录职责','','| 目录 | 阅读用途 |','| --- | --- |','| backend | ERP基座、履约模块、Mapper/JDBC、V1—V8及规则单测 |','| frontend | 履约/核对/消息/文件/仓库页面与请求精度 |','| tests | 真实HTTP/SQL、进程故障、多JVM、迁移、性能和交付验收 |','| scripts/deploy | 独立依赖、构建迁移、Broker和包运行 |','| 学习资料/10-验收证据 | 原结果、产物身份和例外，历史JSON保留 |','| 学习资料/05-设计决策与复盘 | 固定来源与单一ADR正文 |','','静态读取文件数：'+str(len(rows))+'；各顶层计数：'+json.dumps(counts,ensure_ascii=False)+'。','','## 文件、行数和声明入口','','| 文件 | 行数 | 主要声明 |','| --- | --- | --- |']
    for row in rows:
        p=ROOT/row['path'];labels='、'.join(s['name']+':'+str(s['line']) for s in row['symbols'][:12]) or '配置/SQL/记录/脚本主流程'
        out.append(f'| [{row["path"]}]({portable(p)}) | {row["lines"]} | {labels} |')
    out+=['','完整SHA及声明位置见[项目审阅快照](项目审阅快照.json)。上游来源与实际二开范围见[M7源码差异](../10-验收证据/M7-source-diff.json)，不是Git提交diff或个人独立掌握证明。']
    write(INDEX/'项目文件与源码清单.md','\n'.join(out))
    return rows,diff

def readmes():
    for folder,title,scope in [(STUDY,'完整项目系统学习教程','按编号学习；25—30补齐核对、消息、文件、授权、性能、交付。'),(QA,'完整项目面试问答','192道专题问答加40道综合题；F组是已完成能力与可选扩展。')]:
        out=['# '+title,'','2026-10-20，依据最终M0—M7/V8。'+scope+' 本轮仅核对资料，没有重跑业务或压测。','','[返回总目录](../README.md)','','| 章节 | 文件 |','| --- | --- |']
        for p in sorted(folder.glob('*.md')):
            if p.name=='README.md':continue
            text=p.read_text(encoding='utf-8');name=re.search(r'^# (.+)',text,re.M).group(1)
            out.append(f'| {p.stem.split("-")[0]} | [{name}]({p.name}) |')
        out+=['','先业务数量，再事务与源码，再失败证据和追问。旧阶段报告保留历史语境，当前状态看总目录和PROJECT_STATUS；“已做”必须有代码和证据，“我负责”必须符合个人实际参与与掌握。']
        write(folder/'README.md','\n'.join(out))
    for folder,title in [('03-阶段原理讲解','M0—M7阶段原理'),('05-设计决策与复盘','设计决策与复盘')]:
        path=PACK/folder;out=['# '+title,'','正文保留当时阶段的需求/取舍/失败与限制。早期“后续阶段待做”是历史语境；当前M0—M7已完成，完整现行教程见[01](../01-系统学习教程/README.md)。设计决策正文只保留一份；原路径和恢复方式见整理清单。','']
        for p in sorted(path.glob('*.md')):
            if p.name=='README.md':continue
            out.append('- ['+p.stem+']('+p.name+')')
        write(path/'README.md','\n'.join(out))

def main():
    INDEX.mkdir(parents=True,exist_ok=True)
    rows,diff=inventory();readmes()
    checks=[]
    def check(name,ok,detail=None):checks.append({'name':name,'passed':bool(ok),'detail':detail})
    errors=[];links=lines=jsons=0
    docs=list(PACK.rglob('*.md'))+[ROOT/'README.md',legacy('docs/AI_IMPLEMENTATION_SPEC.md'),legacy('docs/PROJECT_STATUS.md'),legacy('docs/LEARNING_AND_INTERVIEW_GUIDE.md')]
    for p in docs:
        raw=p.read_bytes();text=raw.decode('utf-8-sig')
        if '\ufffd' in text or raw.count(b'\r\r\n') or len(re.findall(r'^```',text,re.M))%2:errors.append(str(p)+': encoding/fences')
        if re.search(r'^\|[^\n]+\|\n\n\|',text,re.M):errors.append(str(p)+': blank line breaks Markdown table')
        for body in re.findall(r'^```json\s*\n(.*?)^```',text,re.M|re.S):
            try:json.loads(body);jsons+=1
            except ValueError:errors.append(str(p)+': JSON example')
        for target in re.findall(r'\[[^\]\n]+\]\(([^)\n]+)\)',clean(text)):
            target=target.strip('<>')
            if urlsplit(target).scheme or target.startswith('//'):continue
            name,sep,fragment=unquote(target).partition('#');dest=(p.parent/name).resolve() if name else p;links+=1
            if not dest.exists():errors.append(f'{os.path.relpath(p,ROOT)} -> missing {target}');continue
            if not fragment or dest.is_dir():continue
            if re.fullmatch(r'L\d+',fragment):
                lines+=1
                if not 1<=int(fragment[1:])<=len(dest.read_text(encoding='utf-8-sig').splitlines()):errors.append(str(p)+': source line '+target)
            elif dest.suffix=='.md' and fragment not in anchor_set(dest.read_text(encoding='utf-8-sig')):errors.append(str(p)+': anchor '+target)
    check('文档编码围栏JSON表格链接锚点',not errors,errors)
    questions=[];bad=[]
    for p in QA.glob('*.md'):
        text=p.read_text(encoding='utf-8');matches=list(re.finditer(r'^## ([A-Z]\d{2}) (.+)$',text,re.M))
        for i,m in enumerate(matches):
            questions.append(m.group(1));body=text[m.start():matches[i+1].start() if i+1<len(matches) else len(text)]
            if any(f'**{x}：**' not in body for x in ['短答','展开','继续追问','易错','定位']):bad.append(m.group(1))
    check('192专题题号唯一且五段完整',len(questions)==192 and len(set(questions))==192 and not bad,bad)
    composite=PACK/'04-演示简历与复习/04-综合面试追问.md'
    composite_count=len(re.findall(r'^### \d+\.',composite.read_text(encoding='utf-8'),re.M))
    check('综合追问40道独立保留',composite_count==40,composite_count)
    drift=[]
    for e in diff['files']:
        p=legacy(e['path'])
        if not p.exists() or digest(p)!=e['current_sha256']:drift.append(e['path'])
    check('相对M7源码差异归档的175份业务源文件未改变',not drift,drift)
    manifest=json.loads((PACK/'整理迁移清单.json').read_text(encoding='utf-8'));archive=legacy(manifest['archive'])
    check('整理前ZIP摘要保持',digest(archive)==manifest['archive_sha256'])
    with zipfile.ZipFile(archive) as z:
        check('整理前75份源资料逐字节可恢复',z.testzip() is None and all(hashlib.sha256(z.read(e['old'])).hexdigest()==e['original_sha256'] for e in manifest['entries']))
    # Capture immutable evidence and SQL before final documentation-only checks.
    protected_file=INDEX/'受保护原件快照.json'
    protected=set(EVIDENCE.rglob('M*'))|set((ROOT/'backend/yudao-module-fulfillment/src/main/resources/db/fulfillment').glob('V*.sql'))
    protected={p for p in protected if p.is_file()}
    current={os.path.relpath(p,ROOT).replace(chr(92),'/'):digest(p) for p in sorted(protected)}
    if not protected_file.exists():write(protected_file,json.dumps({'files':current},ensure_ascii=False,indent=2))
    old=json.loads(protected_file.read_text(encoding='utf-8'))['files'];old={p:h for p,h in old.items() if not p.endswith('.md')};changed=[p for p,h in old.items() if not legacy(p).exists() or digest(legacy(p))!=h]
    check('本轮原M阶段证据与冻结迁移未改',not changed,changed)
    build=json.loads((EVIDENCE/'M7-build.json').read_text(encoding='utf-8'))
    tests=sum(int(s['tests']) for s in build['suites']);check('最终归档JUnit转录60',tests==60,tests)
    perf=json.loads((EVIDENCE/'M7.3-summary.json').read_text(encoding='utf-8'))
    check('性能来源1152查询512库存且每轮32成功32不足',sum(x['samples'] for x in perf['query'])==1152 and sum(x['samples'] for x in perf['stock'])==512 and all(x['outcomes']=={'ALLOCATED':32,'INSUFFICIENT_STOCK':32} and x['errors']==0 for x in perf['stock']))
    ddl=len(re.findall(r'^## ful_\w+$',(STUDY/'20-迁移与数据库字典.md').read_text(encoding='utf-8'),re.M))
    routes=len(re.findall(r'^\| (?:GET|POST|PUT|DELETE) \|',(STUDY/'21-实际接口与请求契约.md').read_text(encoding='utf-8'),re.M))
    check('生成字典含26表和全部路由',ddl==26 and routes>=50,{'tables':ddl,'routes':routes})
    stale=[]
    pattern=r'M[4567](?:\.\d)?[^\n。；]{0,15}(?:未开始|未实施)|当前完成到M4\.2|当前项目没有压测结果|后者待M6'
    for folder in [STUDY,QA]:
        for p in folder.glob('*.md'):
            if re.search(pattern,p.read_text(encoding='utf-8')):stale.append(p.name)
    check('现行教程问答无旧阶段未完成结论',not stale,stale)
    report={'run_at':datetime.now(timezone.utc).isoformat(),'scope':'仅完整学习包静态审阅/结构/源文件哈希/历史数字转录；未运行应用/DB/HTTP/迁移/压测。','result':'passed' if all(c['passed'] for c in checks) else 'failed','metrics':{'markdown_files':len(list(PACK.rglob('*.md'))),'study_chapters':len(list(STUDY.glob('*.md'))),'interview_files':len(list(QA.glob('*.md'))),'topic_questions':len(questions),'comprehensive_questions':composite_count,'local_links':links,'source_line_links':lines,'json_examples':jsons,'read_source_and_evidence_files':len(rows),'protected_files':len(old),'routes':routes,'ddl_tables':ddl},'checks':checks}
    write(EVIDENCE/'DOC-two-folders-learning-20261020.json',json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({'result':report['result'],'metrics':report['metrics'],'failed':[c for c in checks if not c['passed']]},ensure_ascii=False))
    return 0 if report['result']=='passed' else 1

if __name__=='__main__':raise SystemExit(main())
