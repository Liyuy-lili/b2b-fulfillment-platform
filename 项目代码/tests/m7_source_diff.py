"""Verified pinned source archive vs current files, independent of Git status."""
import difflib,hashlib,json,subprocess,zipfile
from datetime import datetime,timezone
from pathlib import Path
import requests
import m7_support as h
lock=json.loads((h.ROOT/'docs/baseline.lock.json').read_text(encoding='utf-8'));cache=h.ROOT/'.local/source-baselines';cache.mkdir(exist_ok=True)
E={'run_at':datetime.now(timezone.utc).isoformat(),'scope':'Pinned upstream archives versus current backend/frontend source; text unified diff, not Git commit diff. Root docs/tests/deploy are separately inventoried.','sources':[],'files':[]}
patch=[]
for source in lock['sources']:
    directory=source['directory'];repo=source['repository'].split('github.com/')[1];archive=cache/(directory+'-'+source['commit']+'.zip');url='https://codeload.github.com/'+repo+'/zip/'+source['commit']
    if not archive.exists():
        with requests.get(url,stream=True,timeout=(15,120)) as response:
            response.raise_for_status()
            with archive.open('xb') as output:
                for chunk in response.iter_content(1024*1024):output.write(chunk)
    assert h.sha(archive)==source['archive_sha256'],str(archive)+' pinned archive hash differs'
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None;baseline={}
        for info in z.infolist():
            if info.is_dir():continue
            name=info.filename.split('/',1)[1];baseline[name]=z.read(info)
        args=['rg','--files','--hidden','-g','!**/target/**','-g','!**/node_modules/**','-g','!**/dist/**','-g','!**/dist-*/**','-g','!**/.git/**','-g','!**/__pycache__/**',directory]
        result=subprocess.run(args,cwd=h.ROOT,capture_output=True,text=True,encoding='utf-8',check=True)
        current={Path(n).relative_to(directory).as_posix() for n in result.stdout.splitlines()}
        counts={'upstream':len(baseline),'added':0,'modified':0,'missing':0,'unchanged':0}
        for name in sorted(set(baseline)|current):
            old=baseline.get(name);path=h.ROOT/directory/name;new=path.read_bytes() if path.is_file() else None
            if old==new:counts['unchanged']+=1;continue
            status='added' if old is None else 'missing' if new is None else 'modified';counts[status]+=1
            entry={'path':directory+'/'+name,'status':status,'upstream_sha256':hashlib.sha256(old).hexdigest() if old is not None else None,'current_sha256':hashlib.sha256(new).hexdigest() if new is not None else None};E['files'].append(entry)
            try:
                a=old.decode('utf-8').splitlines() if old else [];b=new.decode('utf-8').splitlines() if new else []
                patch.extend(difflib.unified_diff(a,b,fromfile='upstream/'+directory+'/'+name if old else '/dev/null',tofile='current/'+directory+'/'+name if new else '/dev/null',lineterm=''))
            except UnicodeDecodeError:entry['binary']=True
        assert counts['missing']==0,(directory,counts)
        E['sources'].append({'directory':directory,'commit':source['commit'],'archive_sha256':h.sha(archive),'archive_url':url,'counts':counts})
dest=h.OUT/'M7-upstream-to-current.patch';dest.write_text('\n'.join(patch)+'\n',encoding='utf-8');E.update(patch=dest.name,patch_sha256=h.sha(dest),result='passed');h.save('M7-source-diff.json',E)
md=['# 固定上游到当前源码的二次开发差异','','这是对已校验SHA256的固定提交源码ZIP进行逐文件比较，不依赖当前目录是否已经提交Git，也不冒充个人独立编写证明。文本diff用于阅读；二进制以哈希记录。根目录测试、部署、DDL补充和文档见各阶段changes清单。','','[完整差异JSON](../evidence/M7-source-diff.json) · [统一文本diff](../evidence/M7-upstream-to-current.patch)','','| 源码 | 固定提交 | 新增 | 修改 | 缺失 |','| --- | --- | --- | --- | --- |']
for source in E['sources']:
    c=source['counts'];md.append(f"| {source['directory']} | {source['commit']} | {c['added']} | {c['modified']} | {c['missing']} |")
md+=['','## 阅读顺序','','1. 先看新增履约模块及V1—V8，理解新领域事实。','2. 再看ERP库存Mapper/Service、托管源单保护和内部适配，理解旧入口如何闭合。','3. 再看frontend履约/核对/文件/仓库工作台和API，区分原管理端壳与新业务。','4. 最后看POM、依赖锁和环境配置，区分运行适配与业务贡献。','','## 新增或修改的源码','','| 类型 | 文件 |','| --- | --- |']
for file in E['files']:md.append('| '+file['status']+' | ['+file['path']+'](../../'+file['path']+') |')
(h.ROOT/'../学习资料/04-演示简历与复习/06-实际源码差异.md').write_text('\n'.join(md)+'\n',encoding='utf-8');print('Pinned-source comparison passed',len(E['files']),flush=True)
