"""Generate reports from completed current evidence; no estimated figures."""
import json,re,statistics,math
from datetime import datetime,timezone
import m7_support as h
CASES=['core','expiry','returns','reconcile','message','filefoundation','file']
SHA=h.load('M7-build.json')['backend_sha256'];runs={c:h.load('M7.2-'+c+'-run.json') for c in CASES}
assert all(r['result']=='passed' and r['artifact_sha256']==SHA and r['all_owned_stopped'] for r in runs.values())
# Correct an overbroad adapter description while retaining the original meta.
# The historical child-report collision is disclosed, not silently erased.
for case,run in runs.items():
    if any(isinstance(x,str) and 'historical evidence files are never replaced' in x for x in run['adaptations']):
        original=h.OUT/('M7.2-'+case+'-original-meta.json')
        if not original.exists():original.write_bytes((h.OUT/('M7.2-'+case+'-run.json')).read_bytes())
        run['adaptations']=[x.replace('historical evidence files are never replaced.','historical primary reports retained; one historical child-report collision is disclosed in M7-evidence-exception.json.') if isinstance(x,str) else x for x in run['adaptations']]
        run['metadata_description_correction']={'original':original.name,'exception':'M7-evidence-exception.json','reason':'Initial preservation description was too broad; no business assertions or suite counts changed.'}
        h.save('M7.2-'+case+'-run.json',run)
# Early adapters retained historical descriptive fields although Popen forced
# DB12 and mapped ports. Preserve raw JSON and correct only those labels;
# business checks/results and actual request evidence are not changed.
for case,run in runs.items():
    for item in run['results']:
        name=item['evidence'];data=h.load(name);corrections={}
        if 'artifact_sha256' not in data:data['artifact_sha256']=SHA
        if data.get('redis_database')!=12:corrections['redis_database']=data.get('redis_database');data['redis_database']=12
        if 'instances' in data and any('48080' in x for x in data['instances']):
            corrections['instances']=data['instances'];data['instances']=['http://127.0.0.1:48082','http://127.0.0.1:48083']
        if corrections:
            raw=h.OUT/(name.removesuffix('.json')+'-original-labels.json')
            if not raw.exists():raw.write_bytes((h.OUT/name).read_bytes())
            data['metadata_correction']={'original_labels':corrections,'reason':'M7 runner Popen forces Redis DB12 and maps core normal instances to48082/48083; no business assertion changed.','raw':raw.name};h.save(name,data)
matrix=[
('T01',['filefoundation','M7-final-release'],r'history|clean install|normal application restart'),('T02',['core-ERP'],r'Ledger sum matches stock|Physical inventory balance'),
('T03',['core-binding'],r'bind|binding'),('T04',['core-m2'],r'both JVM|one saved|same.key'),('T05',['core-m2'],r'conflict'),
('T06',['core-m2'],r'limited.stock race'),('T07',['core-m2'],r'no partial commitment survives'),('T08',['core-m2'],r'single first|priority determines'),
('T09',['core-m3'],r'ship deducts|partial shipment'),('T10',['core-m3','core-erp-fault'],r'rolls.back|rollback|fault'),('T11',['core-m3'],r'ship versus cancel'),
('T12',['expiry'],r'ship|expiry|expire'),('T13',['core-legacy'],r'purchase|transfer|stock|inventory|调拨|盘|退'),('T14',['core-binding','core-m3'],r'managed|frozen|bypass'),
('T15',['core-m3'],r'duplicate callback|late transit|callback conflict'),('T16',['core-m3','core-m3-permissions'],r'signature|integration'),('T17',['returns'],r'receiv|exceed|limit|over'),
('T18',['message'],r'M7 enabled workers|M7 restoring application'),('T19',['message'],r'after.confirm|publisher lease'),('T20',['message'],r'consumer commit before ACK|Inbox committed before ACK|redelivered ACK crash'),
('T21',['message','file'],r'old (publisher|artifact) cannot overwrite'),('T22',['file'],r'committed first row|reuses original|exit81'),('T23',['file'],r'10MiB|10000|precision|invalid|UTF'),
('T24',['core-binding','file'],r'foreign tenant|other tenant|cross.tenant'),('T25',['file'],r'projection has no financial|detail excludes prices|unauthorized warehouse'),('T26',['file'],r'reused worker thread clears'),('T27',['file'],r'download rechecks revoked'),
('T28',['core-m2'],r'T28 concurrent first insert'),('T29',['core-m2'],r'large|decimal|unit|precision'),('T30',['reconcile'],r'corrupt|difference|restore|missing')]
spec=(h.ROOT/'../学习资料/09-项目规范与进度/AI_IMPLEMENTATION_SPEC.md').read_text(encoding='utf-8');rows=[]
for ident,names,pattern in matrix:
    proof=[]
    for name in names:
        file=(name if name.startswith('M7-') else 'M7.2-'+name)+'.json';data=h.load(file);assert data.get('result',data.get('status'))=='passed'
        matches=[c['name'] for c in data['checks'] if c['passed'] and re.search(pattern,c['name'],re.I)];assert matches,(ident,file,pattern)
        proof.append({'file':file,'assertions':matches})
    description=re.search(r'\| '+ident+r' \| ([^|]+)',spec).group(1).strip();rows.append({'id':ident,'scenario':description,'passed':True,'proof':proof})
h.save('M7.2-matrix.json',{'run_at':datetime.now(timezone.utc).isoformat(),'artifact_sha256':SHA,'result':'passed','scenarios':rows,'suite_results':runs,'boundary':'T18 uses actual connection-refused port with workers enabled; shared Broker process remains running. Exact process restart is separately covered by final main restart.'})
md=['# M7.2：最终产物集成与故障矩阵','','当前jar SHA256：`'+SHA+'`。所有下列断言是本轮新库执行。历史主验收报告保留；一份子报告命名覆盖例外见下文。','','| 场景 | 当前证据 | 具名断言示例 |','| --- | --- | --- |']
for row in rows:
    md.append('| '+row['id']+' '+row['scenario']+' | '+'、'.join('['+p['file']+']('+p['file']+')' for p in row['proof'])+' | '+'；'.join(p['assertions'][0].replace('|','/') for p in row['proof'])+' |')
md+=['','## 本轮套件','','| 套件 | 当前断言数 | 数据库 |','| --- | --- | --- |']
for case,run in runs.items():md.append('| '+case+' | '+str(sum(x['checks'] for x in run['results']))+' | `'+run['database']+'` |')
md+=['','## 改动与边界','','隔离schema、Redis DB12与48082—48084；同jar、原测试源码SHA及适配清单见各run.json。正向普通操作者通过真实授权接口补OPERATE，负向用户未扩大授权。迁移期望V0—V8，业务断言保留。T18新增真实连接拒绝启动/发货/恢复，不把旧工作者关闭的NEW检查冒称Broker停机；本轮未为它停共享Broker。','', '首轮core因为通用启动器关闭到期扫描，未满足旧M3的自然到期前提而失败；修正启用扫描后在新库完整重跑。失败JSON/日志保留，不抹去失败历史。指定60个JUnit、T01—T30和细粒度断言是不同计数口径，不相加伪造覆盖率。']
md+=['','## 证据归档例外','','旧退货测试在子进程环境写死M4.2-clean-binding.json，初版适配只覆盖了到期用例的另一文件名，导致该历史子JSON被本轮M7退货库的68项绑定回归覆盖。本轮内容已另存[M7.2-returns-binding.json](M7.2-returns-binding.json)，旧路径显式增加provenance_warning；[例外记录](M7-evidence-exception.json)说明原因和修复。旧子报告原始内容未能本地恢复，不能声称历史文件全部逐字保留。M4.2主要验收、升级和重启报告保留，不伪造旧数据恢复。后续适配已增加独立文件名。']
md+=['','## 首轮失败与修复','','消息首轮在已通过真实exit71/72和fencing后，M5普通Owner正向用例因缺少M6仓库OPERATE被正确拒绝；补真实授权并新库完整重跑，其他负向用户不扩大权限。T18独立传输测试关闭到期扫描，避免与已经另行验证的到期定时变化混合。']
md+=['','文件基础与核心共享同一个SQL测试库，编排器首轮却在两者之间清空Redis DB12，造成ERP单号序列丢失，采购入库被唯一约束正确拒绝。已取消file前的清空，通过[序列修复记录](M7.2-sequence-repair.json)只向上恢复测试DB12的序列；修复前后全部ERP/ful业务行摘要一致，没有改业务SQL或主DB0。随后同一foundation库完整重跑文件核心104项通过。此为测试编排缺陷，不能把SQL库与单号序列当成互不相关的状态。']
for p in sorted(h.OUT.glob('M7.2-*-failed-*.json')):md.append('- ['+p.name+']('+p.name+')：保留失败时数据库/错误/源码与日志索引；其通用result文件名在同阶段重跑后指向当前结果，不作为首轮详细结果的不可变副本。')
(h.OUT/'M7.2-验收报告.md').write_text('\n'.join(md)+'\n',encoding='utf-8')

query=h.load('M7.3-query.json');stock=h.load('M7.3-stock.json');assert query['result']==stock['result']=='passed' and query['artifact_sha256']==stock['artifact_sha256']==SHA
per=[]
for concurrency in [4,8]:
    for mode in ['before','after']:
        phases=[x for x in query['rounds'] if x['mode']==mode and x['concurrency']==concurrency];assert len(phases)==3
        raw=[r for phase in phases for r in phase['requests']];v=sorted(r['ms'] for r in raw);pct=lambda p:v[math.ceil(len(v)*p)-1]
        stats={'mode':mode,'concurrency':concurrency,'samples':len(v),'p50_ms':pct(.5),'p95_ms':pct(.95),'p99_ms':pct(.99),'requests_per_second':len(v)/sum(p['summary']['seconds'] for p in phases),'errors':sum(p['summary']['errors'] for p in phases),'rows_examined':sum(s['rows_examined'] for p in phases for s in p['sql_delta']),'select_count':sum(s['count'] for p in phases for s in p['sql_delta'])};per.append(stats)
h.save('M7.3-summary.json',{'artifact_sha256':SHA,'query':per,'stock':[{'repeat':r['repeat'],'concurrency':r['concurrency'],**r['summary'],'outcomes':r['outcomes'],'mysql_global_delta':r['mysql_global_delta']} for r in stock['rounds']],'exports':[{k:v for k,v in e.items() if k!='resources'} for e in query['exports']],'result':'passed'})
md=['# M7.3：性能实验与索引对比','','原始请求：[查询](M7.3-query.json)、[库存](M7.3-stock.json)、[汇总](M7.3-summary.json)。本报告由实际结果生成，当前jar `'+SHA+'`。','','## 环境与方法','',''+json.dumps(query['environment'],ensure_ascii=False,default=str),'','同一Windows主机、本地负载端、单JVM，MySQL缓冲池128MiB，Druid最大12、JVM堆768MiB。主应用空闲但共享依赖；未测跨机、冷缓存、生产容量或长时间稳定极限。SQL合成查询数据与真实HTTP业务验收分开。','', '## 查询实测','','每组3轮，每轮热身20、采样96；状态WAIT_STOCK，page1/page80各半，pageSize50。前后交替顺序，逐请求ID/总量一致且另一租户隔离。INVISIBLE仍维护索引，只模拟旧可用读索引集合。','','| 并发 | 索引 | 样本 | P50 ms | P95 ms | P99 ms | 请求/s | 错误 | SELECT次数 | rows_examined |','| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
for r in per:md.append('| '+' | '.join([str(r['concurrency']),r['mode'],str(r['samples']),f"{r['p50_ms']:.2f}",f"{r['p95_ms']:.2f}",f"{r['p99_ms']:.2f}",f"{r['requests_per_second']:.2f}",str(r['errors']),str(r['select_count']),str(r['rows_examined'])])+' |')
md+=['','before/after的EXPLAIN JSON与ANALYZE完整文本在查询原始JSON plans；不将估计rows冒称实际扫描。实际SQL次数包含该窗口中匹配ful_order的SELECT摘要，HTTP吞吐包含鉴权、JSON与日志。新索引增加维护/存储成本，未做写入成本对比；页统计为'+json.dumps(query['index_size_pages'],ensure_ascii=False,default=str)+'。','','## 库存竞争','','真实HTTP准备512张订单，每轮64张争抢H32；1/4/8/16并发各重复两轮，先预热8张并释放。全部计时请求须32成功、32不足、0系统错误；每轮R=held=占用流水32，释放后R0，H恒32且等于实物流水。最终全租户核对0差异。','','| 轮 | 并发 | P95 ms | P99 ms | 请求/s | 预占/不足 | 锁等待次数/毫秒 |','| --- | --- | --- | --- | --- | --- | --- |']
for r in stock['rounds']:
    d=r['mysql_global_delta'];md.append(f"| {r['repeat']} | {r['concurrency']} | {r['summary']['p95_ms']:.2f} | {r['summary']['p99_ms']:.2f} | {r['summary']['requests_per_second']:.2f} | {r['outcomes']} | {d.get('Innodb_row_lock_waits')}/{d.get('Innodb_row_lock_time')} |")
md+=['','锁计数为共享MySQL全局增量，不严格归因到单个请求。库存竞争仅测当前正确锁方案，没有为凑提升比例更改锁序/事务。','','## 大文件导出观测','','| 状态 | 行数含表头/说明 | 字节 | 受理至下载秒 | 采样堆峰KiB | RSS峰字节 | GC增量 |','| --- | --- | --- | --- | --- | --- | --- |']
for e in query['exports']:
    r=e['resources'];md.append(f"| {e['mode']} | {e['xlsx_rows_including_headers']} | {e['bytes']} | {e['seconds']:.2f} | {r['heap_sample_peak_kib']:.0f} | {r['rss_peak_bytes']} | {r['gc_delta']} |")
md+=['','导出每状态一次，是端到端资源观测，不支持统计性的提速百分比。每0.5秒采样加jstat开销，峰值是采样下界，RSS不是Java堆。实际XLSX与SHA、无公式检查、逐阶段CPU/RSS/GC原始采样均保留。','', '## 面试可以怎样表述','','“在固定多租户合成数据和同JVM交替实验下，对订单状态分页定位执行计划并新增联合索引，保存实际扫描行与端到端样本；库存竞争按业务成功/不足分开统计，并核对余额与流水。”具体数字只引用表中条件，不推广成生产容量。']
(h.OUT/'M7.3-性能报告.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
print('M7 reports generated from completed evidence')
