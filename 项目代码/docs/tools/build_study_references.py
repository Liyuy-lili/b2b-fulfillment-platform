"""Build source-derived study appendices; never start services or run business tests.

Run from any directory: python docs/tools/build_study_references.py
Only the named generated reference documents and snapshot are replaced.
"""
from __future__ import annotations

import os
from project_layout import PACK, EVIDENCE, legacy
import hashlib
import json
import re
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
STUDY = PACK / '01-系统学习教程'
QA = PACK / '02-面试问答'
FUL = ROOT / 'backend/yudao-module-fulfillment/src/main/java/cn/iocoder/yudao/module/fulfillment'
ERP = ROOT / 'backend/yudao-module-erp/src/main/java/cn/iocoder/yudao/module/erp'
SQL = ROOT / 'backend/yudao-module-fulfillment/src/main/resources/db/fulfillment'
INPUTS: set[Path] = set()


def read(path: Path) -> str:
    INPUTS.add(path)
    return path.read_text(encoding='utf-8-sig')


def relative(path: Path) -> str:
    return os.path.relpath(path, ROOT).replace(chr(92), '/')


def link(path: Path, label: str | None = None, line: int | None = None) -> str:
    target = os.path.relpath(path, STUDY).replace(chr(92), '/')
    if line:
        target += '#L' + str(line)
    return f'[{label or path.name}]({target})'


def cell(value: object) -> str:
    return str(value).replace('|', '\\|').replace('\r', '').replace('\n', ' ')


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + '\n', encoding='utf-8')


def source_navigation() -> None:
    groups = {
        '履约HTTP入口与请求契约': sorted((FUL / 'controller').rglob('*.java')),
        '事务服务与领域计算': sorted((FUL / 'service').glob('*.java')) + sorted((FUL / 'domain').glob('*.java')),
        '到期、迁移与故障隔离': sorted((FUL / 'framework').glob('*.java')) + sorted((FUL / 'integration').glob('*.java')),
        '实际锁与SQL入口': sorted((FUL / 'dal/mysql').glob('*.java')),
        'ERP托管和共享库存改造': sorted((ERP / 'service/sale/managed').glob('*.java')) + [
            ERP / 'service/stock/DatabaseCommandRetry.java', ERP / 'service/stock/ErpTransactionRetryAspect.java',
            ERP / 'service/stock/ErpStockServiceImpl.java', ERP / 'service/stock/ErpStockRecordServiceImpl.java',
            ERP / 'dal/mysql/stock/ErpStockMapper.java', ERP / 'dal/mysql/stock/StockKey.java',
            ERP / 'service/sale/ErpSaleOutServiceImpl.java', ERP / 'service/sale/ErpSaleReturnServiceImpl.java',
            ERP / 'service/sale/ErpSaleOrderServiceImpl.java', ERP / 'service/product/ErpProductServiceImpl.java'],
        '前端业务与接口': [p for p in (ROOT / 'frontend/src/views/erp').rglob('*.vue') if any(x in p.parts for x in ['fulfillment','fulfillment-jobs','fulfillment-warehouse','reconciliation'])] + [ROOT / 'frontend/src/api/erp/fulfillment/index.ts'],
        '领域单测': sorted((ROOT / 'backend/yudao-module-fulfillment/src/test').rglob('*.java')),
        '集成验收与运行入口': sorted((ROOT / 'tests').glob('m*.py')) + sorted((ROOT / 'tests').glob('*.ps1')) + sorted((ROOT / 'scripts').glob('*.ps1')),
    }
    out = ['# 19 真实代码导航', '', '生成依据：当前磁盘源文件，2026-10-20整理；行号只是快照，不表示本轮编译或运行。点击源文件链接查看，#L为源码位置提示；不支持行跳转的阅读器可按方法名搜索。', '',
           '## 建议跟踪的五条完整调用链', '',
           '1. 绑定：FulOrderController.bind → FulOrderService.bind → FulCommandService → ErpManagedOrderGuard → 订单/项Mapper。',
           '2. 分配：FulAllocationController.allocate → DatabaseCommandRetry → FulAllocationService.allocate → lockOrder/lockStocks → AllocationPlanner → changeReserved/预占/流水/响应。',
           '3. 发货：FulExecutionController.ship → Retry → FulExecutionService.ship → ErpManagedSaleOutPort → ERP审核/公共库存流水 → 发货/项映射。',
           '4. 到期：FulExpiryScanner.scan → TenantUtils/Retry → FulExpiryService.expire → 系统命令/源单/订单/预占/库存 → 剩余held回open。',
           '5. 退货：FulReturnController → Retry → FulReturnService.create/receive/reject → 原发货/额度 → ErpManagedSaleReturnPort → ERP入库/映射/returned。', '']
    method_pattern = re.compile(r'^\s*(?:public|protected|private)\s+(?:(?:static|final|synchronized)\s+)*(?!class\b|interface\b|record\b)([\w<>,.?\[\] ]+)\s+(\w+)\s*\(')
    for heading, paths in groups.items():
        out += [f'## {heading}', '', '| 文件 | 实际方法或阅读位置 |', '| --- | --- |']
        for path in paths:
            content = read(path)
            methods = []
            if path.suffix == '.java':
                for n, line_text in enumerate(content.splitlines(), 1):
                    match = method_pattern.match(line_text)
                    if match:
                        methods.append(link(path, f'{match.group(2)}:{n}', n))
            elif path.suffix == '.py':
                for n, line_text in enumerate(content.splitlines(), 1):
                    match = re.match(r'^def (\w+)\(', line_text)
                    if match and (match.group(1).startswith('test') or match.group(1) in {'main','check','start','run','snapshot','verify','stop','assert_invariants'}):
                        methods.append(link(path, f'{match.group(1)}:{n}', n))
            if not methods:
                methods = ['阅读文件中的声明、配置或脚本主流程']
            out.append(f'| {link(path)} | {"、".join(methods)} |')
        out.append('')
    out += ['## 阅读时避免的混淆', '', 'DO是数据库表示，Contracts是HTTP表示；Planner不访问数据库；Service是事务业务；Port是同应用能力边界。framework目录的故障Bean只用于专用测试profile；发现其存在不等于生产请求能触发。', '', '旧M0调用链记录的行号和方法名是历史快照，现行库存入口看这里及当前源码。']
    write(STUDY / '19-真实代码导航.md', '\n'.join(out))


def schema_reference() -> None:
    purposes = {
        'ful_order': 'ERP源单一对一执行主单，快照/owner/状态/策略/版本。',
        'ful_order_item': '逐原销售项的商品单位和价格快照、执行数量恒等式。',
        'ful_reservation': '订单项分仓承诺、剩余/消费/释放量与期限。',
        'ful_shipment': '一次单仓发货，ERP出库映射与配送状态。',
        'ful_shipment_item': '原订单项、预占与ERP出库项的逐笔发出数量。',
        'ful_command_record': '租户/操作者/动作/key下的摘要和持久化原响应。',
        'ful_stock_ledger': '预占变动流水；实物变化仍以ERP流水为准，不能双加。',
        'ful_callback_event': '物流provider/eventId去重、业务摘要和冲突诊断。',
        'ful_warehouse_grant': 'V1建表，M6已接入READ/OPERATE、专用投影和相关操作授权。',
        'ful_cancellation': '逐项取消原因、数量、操作号和操作者。',
        'ful_return': '一原发货、一原仓的申请/收货/拒绝状态与ERP退货映射。',
        'ful_return_item': '原发货项额度与实际退货项/实物流水映射。',
        'ful_reconcile_run': '一次全租户、本人报告：规则版本、读取起始标记、各表行数和差异计数；不是历史库存截止时点。',
        'ful_reconcile_item': '某条规则发现的对象、关联ID、expected/actual与说明；确认不改原事实。',
        'ful_reconcile_review': '核对差异的追加人工说明，保存actor和请求身份，ACKNOWLEDGED不表示修复。',
        'ful_outbox_event': '与业务同事务提交的不可变执行事件；状态、次数和owner/version/until控制可靠发布。',
        'ful_outbox_delivery': '同eventId的逐次发布尝试，lease版本隔离ACKED/FAILED/EXPIRED/LATE；不是新业务事件。',
        'ful_inbox_event': 'tenant+consumer+event去重、消费状态/次数/持久化重试责任；投影与正常处理共同提交。',
        'ful_order_read_model': '可重建的执行快照，observed_version单调保护；不是库存事实来源。',
        'ful_message_action': '重新发布、消费重试、读模型重建的原因/操作者/请求和前后状态审计。',
        'ful_job_gate': '数据库全局/租户准入及租户运行配额的行锁门闩；不是线程池队列。',
        'ful_private_file': '私有输入/结果/错误文件的归属、服务端storageKey、大小及SHA；不直接暴露路径。',
        'ful_file_job': '持久化任务、冻结scope/maxId、进度/状态/文件引用及owner/version租约。',
        'ful_file_job_row': 'CSV任务逐行解析内容、成功/失败和ERP草稿关联；与业务身份及成功副作用同事务。',
        'ful_import_identity': 'tenant/sourceSystem/externalNo跨任务行业务去重，规范化内容hash和归属防冲突/盗用。',
        'ful_operation_audit': '任务/文件下载/仓库授权等操作的actor、对象、原因、请求与前后状态。',
    }
    out = ['# 20 实际迁移与数据库字典', '', '由V1—V8源文件提取，不连接数据库。类型/默认值/索引以原SQL和实际迁移验收为准；同一表后续ALTER需要一起读。下列CREATE列清单描述创建时定义，V2—V8增量单独列出，不能把它当最终SHOW CREATE TABLE。', '', '## 迁移原文与表职责', '', '| 迁移 | CREATE表 |', '| --- | --- |']
    migrations = []
    tables = []
    for path in sorted(SQL.glob('V*.sql')):
        text = read(path)
        migrations.append((path, text))
        matches = list(re.finditer(r'CREATE TABLE\s+([\w]+)\s*\((.*?)\) ENGINE=.*?;', text, re.S))
        out.append(f'| {link(path)} | {"、".join(m.group(1) for m in matches) or "无新表"} |')
        tables.extend((path, m.group(1), m.group(2), text[:m.start()].count('\n') + 1) for m in matches)
    out += ['', '## 三条业务数量约束', '', '`H≥R≥0`；`ordered=open+reserved+shipped+cancelled`且`0≤returned≤shipped`；`allocated=held+consumed+released`。跨行额度、库存R/held汇总和ERP映射完整性还需事务协议与核对，CHECK并不自动覆盖全部关系。', '']
    for path, table, body, line in tables:
        out += [f'## {table}', '', purposes.get(table, ''), '', f'创建来源：{link(path, path.name + ":" + str(line), line)}。', '', '| 列 | 创建时SQL定义 |', '| --- | --- |']
        constraint_chunks = []
        # Split only top-level commas; decimal parameters and key columns stay intact.
        depth = 0
        quote = None
        current = ''
        chunks = []
        for ch in body:
            if quote:
                current += ch
                if ch == quote:
                    quote = None
                continue
            if ch in {"'", '"', '`'}:
                quote = ch
            elif ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
            elif ch == ',' and depth == 0:
                chunks.append(current.strip()); current = ''; continue
            current += ch
        if current.strip():
            chunks.append(current.strip())
        for chunk in chunks:
            match = re.match(r'`?(\w+)`?\s+(BIGINT|VARCHAR|DECIMAL|INT|DATETIME|BIT|TINYINT|SMALLINT|BOOLEAN|JSON|TEXT|CHAR)\b', chunk, re.I)
            if match:
                out.append(f'| `{match.group(1)}` | `{cell(chunk[len(match.group(1)):].strip())}` |')
            else:
                constraint_chunks.append(chunk)
        out += ['', '创建时键与约束：', '', '```sql', ',\n'.join(constraint_chunks), '```', '']
    out += ['## 后续ALTER原文：需要叠加到上面CREATE', '']
    for path, text in migrations:
        statements = re.findall(r'ALTER TABLE\s+.*?;', text, re.S)
        if statements:
            out += [f'### {path.name}', '', f'来源：{link(path)}。', '', '```sql', '\n\n'.join(statements), '```', '']
    out += ['## ERP和迁移历史入口', '', f'- ERP基础DDL：{link(ROOT / "deploy/sql/010-erp.sql")}，33表由项目推导补齐，保留来源边界。', f'- ERP实体清单：{link(ROOT / "deploy/erp-entities.json")}。', f'- 显式接管与迁移：{link(ROOT / "scripts/Migrate-Database.ps1")}。', '', 'V1—V8已在已登记数据库执行，后续只新增迁移。M4.3核对、M5消息、M6任务/授权均已完成；创建时字段必须叠加后续ALTER。']
    write(STUDY / '20-迁移与数据库字典.md', '\n'.join(out))


def api_reference() -> None:
    out = ['# 21 实际接口、请求契约与错误码', '', '从当前Controller/Contracts源码提取，未发送请求。管理前缀/admin-api、应用前缀/app-api按基座包映射；页面请求封装通常省略此前缀。Controller实际存在才算当前接口，规格未来接口不混入。', '', '## 当前控制器路由', '', '| HTTP | 实际外部路径 | 功能权限/认证 | Java入口 | key |', '| --- | --- | --- | --- | --- |']
    controllers = sorted((FUL / 'controller').rglob('*Controller.java'))
    for path in controllers:
        content = read(path)
        base = re.search(r'@RequestMapping\("([^"]+)"\)', content).group(1)
        prefix = '/app-api' if '/app/' in path.as_posix() else '/admin-api'
        mappings = list(re.finditer(r'@(Get|Post|Put|Delete)Mapping\((?:value\s*=\s*)?"([^"]+)"', content))
        for i, mapping in enumerate(mappings):
            block = content[mapping.start(): mappings[i + 1].start() if i + 1 < len(mappings) else len(content)]
            method = re.search(r'public\s+[^\n]*?\s+(\w+)\(', block)
            perms = re.findall(r'hasPermission\(\x27([^\x27]+)\x27\)', block)
            auth = ' + '.join(perms) if perms else '配置集成+HMAC（免后台登录）' if path.parent.name == 'app' else '检查Controller中的认证/权限'
            row = [mapping.group(1).upper(), '`' + prefix + base + mapping.group(2) + '`', auth,
                   link(path, path.stem + '.' + (method.group(1) if method else '?'), content[:mapping.start()].count('\n') + 1),
                   'Idempotency-Key' if 'Idempotency-Key' in block else '事件ID' if path.parent.name == 'app' else '—']
            out.append('| ' + ' | '.join(row) + ' |')
    out += ['', '## 编号语义', '', '| 契约 | items中ID指向 |', '| --- | --- |', '| ReleaseLine.reservationId | ful_reservation.id |', '| ShipRequest.items[].id | ful_reservation.id |', '| CancelRequest.items[].id | ful_order_item.id |', '| CreateRequest退货items[].id | ful_shipment_item.id |', '', '租户/actor/ERP商业字段不由客户端任意指定。分配holdSeconds当前60—86400，候选仓1—16；release/ship/cancel/退货items有实际大小及小数规则，以下原契约是准确来源。', '', '## 请求和响应Contracts原文（不含package/import）', '']
    for path in sorted((FUL / 'controller/admin').glob('*Contracts.java')):
        content = read(path)
        start = content.find('public final class')
        out += [f'### {path.name}', '', link(path), '', '```java', content[start:].strip(), '```', '']
    errors = FUL / 'enums/FulfillmentErrors.java'
    out += ['## 当前履约业务错误', '', f'来源：{link(errors)}。HTTP状态与业务code不是同一层，测试应同时检查需要的字段。', '', '| 符号 | 数值code | 消息 |', '| --- | --- | --- |']
    for symbol, number, message in re.findall(r'ErrorCode\s+(\w+)\s*=\s*new ErrorCode\(([\d_]+),\s*"([^"]+)"\)', read(errors)):
        out.append(f'| `{symbol}` | {int(number.replace("_", ""))} | {cell(message)} |')
    out += ['', '数据库锁失败最终BUSY定义在ERP的DatabaseCommandRetry，值1030198000；它不属于上面的履约错误区。', '', '## 教学请求示例（不执行）', '', '数字是格式占位，需换成当前有权访问的真实ID；不同请求中的id不是同一类业务对象。不要直接向已有演示数据重放这些示例。', '', '```json', json.dumps({'orderId': '1', 'strategy': 'PRIORITY_SPLIT', 'warehouseIds': ['1','2'], 'holdSeconds': 3600}, ensure_ascii=False, indent=2), '```', '', '上例用于preview或allocate；只有allocate需要命令key。', '', '```json', json.dumps({'orderId': '1', 'shipmentId': '2', 'items': [{'id': '3', 'quantity': '2.000001'}], 'reason': '商品退回'}, ensure_ascii=False, indent=2), '```', '', '上例是退货create，id=原发货项；receive只需要orderId/returnId；reject还需要reason。', '', '## 没有开放的入口', '', '核对、消息、文件任务、专用仓库路由已列出。没有HTTP自动到期/故障开关，也没有资金退款、跨仓退回或终态撤销。multipart上传按实际Controller处理，下载返回流而非普通JSON。']
    write(STUDY / '21-实际接口与请求契约.md', '\n'.join(out))


def evidence_reference() -> None:
    directory = EVIDENCE
    out = ['# 23 历史验收证据索引', '', '本文件只读取既有证据，不重跑业务、不连接数据库。时间和passed均是文件原记录；不存在的字段显示未记录，不按文件名猜通过。断言数、JUnit用例数与业务场景数不同。', '', '## 各阶段报告与讲解', '', '| 阶段 | 原始报告 | 讲解 |', '| --- | --- | --- |']
    lessons = ['M0-基座与库存调用链.md','M1-订单接管与并发保护.md','M2-预占释放与统一库存保护.md','M3-部分发货取消与物流闭环.md','M4.1-自动到期与重复任务.md','M4.2-退货额度与ERP入库.md']
    lessons += ['M4.3-一致性快照与差异核对.md','M5-可靠消息与故障恢复.md','M6-可恢复文件任务与仓库授权.md','M7-集成性能与交付.md']
    for stage, lesson in zip(['M0','M1','M2','M3','M4.1','M4.2','M4.3','M5','M6','M7'], lessons):
        out.append(f'| {stage} | {link(directory / (stage+"-验收报告.md"))} | {link(PACK / "03-阶段原理讲解" / lesson)} |')
    out += ['', '历史阶段报告中“尚未实现”是当时状态，最新以PROJECT_STATUS与M7为准。M4.2核心之后增加只读查询，最终API文件保留两阶段产物摘要；不能拼成一个构建全跑。', '', '## 所有阶段JSON原记录索引', '', '| 文件 | 原记录状态 | checks中通过/失败/总数 | 原时间字段 |', '| --- | --- | --- | --- |']
    records = {}
    for path in sorted(directory.glob('M*.json')):
        data = json.loads(read(path))
        records[path.name] = data
        if not isinstance(data, dict):
            out.append(f'| {link(path)} | 非对象记录，打开原文 | — | — |'); continue
        status = data.get('result', data.get('status', '未设置统一result/status字段'))
        if not isinstance(status, (str, int, bool, type(None))):
            status = '结构化状态，见原文'
        checks = data.get('checks', [])
        if not isinstance(checks, list):
            checks = []
        passed = sum(isinstance(x, dict) and x.get('passed') is True for x in checks)
        failed = sum(isinstance(x, dict) and x.get('passed') is False for x in checks)
        time = data.get('run_at', data.get('recorded_at', data.get('generated_at', data.get('timestamp', '未记录统一时间字段'))))
        out.append(f'| {link(path)} | {cell(status)} | {passed}/{failed}/{len(checks)} | {cell(time)} |')
    out += ['', '某文件checks为0可能是其他结构、运行快照或构建清单，不代表0项业务检查通过，也不代表失败。请结合原始字段、退出码和阶段报告。', '', '## M7最终产物核心：逐断言名称', '', '这些是已有断言的原名，不是新增运行结果。detail可能很长或包含测试数据，请在原JSON中查看。历史子报告覆盖例外须阅读M7-evidence-exception.json；不将被覆盖的M4.2-clean-binding认作原始M4.2结果。', '']
    for name in ['M7.2-expiry.json', 'M7.2-returns.json', 'M7.2-reconcile.json', 'M7.2-message.json', 'M7.2-file.json']:
        data = records[name]
        out += [f'### {name}', '', link(directory / name), '', '| 序号 | 原断言名称 | passed |', '| --- | --- | --- |']
        for i, check in enumerate(data.get('checks', []), 1):
            out.append(f'| {i} | {cell(check.get("name", "未设置name"))} | {cell(check.get("passed", "未设置passed"))} |')
        out.append('')
    out += ['## M7归档JUnit（实际XML汇总）', '', '| 测试类 | tests | failures | errors | skipped | 原文件 |', '| --- | --- | --- | --- | --- | --- |']
    for path in sorted(directory.glob('M7-junit-*.xml')):
        INPUTS.add(path)
        root = ET.parse(path).getroot()
        attrs = root.attrib
        out.append(f'| {attrs.get("name")} | {attrs.get("tests")} | {attrs.get("failures")} | {attrs.get("errors")} | {attrs.get("skipped")} | {link(path)} |')
    out += ['', '这些是指定单测归档，不是当前工作区新编译结果或全部上游测试。JUnit与脚本断言不可直接相加。', '', '## 怎样选一份证据讲清楚', '', '先说明构建/日期/库和前置，再描述动作与预期，打开checks及detail核对最后事实，最后交代未测条件。正常重启不代表突然断电；同机双JVM不代表跨机；定向前端检查不代表全仓类型检查；测试恒等式不代表核对产品完成。']
    write(STUDY / '23-验收证据索引.md', '\n'.join(out))


def question_index() -> None:
    out = ['# 16 全部题目总索引', '', '由本目录带P/B/D/T/I/L/S/E/R/A/V/C/F编号的二级标题提取。点击可到对应题，F为已完成能力及可选扩展，C为现场学习推演。', '', '| 编号 | 问题 | 主题 |', '| --- | --- | --- |']
    count = 0
    for path in sorted(QA.glob('*.md')):
        if path.name == '16-题目总索引.md':
            continue
        text = path.read_text(encoding='utf-8')
        for code, title in re.findall(r'^## ([A-Z]\d{2}) (.+)$', text, re.M):
            count += 1
            out.append(f'| {code} | [{cell(title)}]({path.name}#{code.lower()}) | {path.stem[3:]} |')
    out += ['', f'实际提取：{count}题。编号计数不代表软件测试数量。']
    composite = PACK / '04-演示简历与复习/04-综合面试追问.md'
    out += ['', '## 另附40道综合追问', '', '以下X编号对应综合篇，和上面192道专题分开统计。', '', '| 编号 | 综合问题 |', '| --- | --- |']
    for number,title in re.findall(r'^### (\d+)\. (.+)$', composite.read_text(encoding='utf-8'), re.M):
        code='X'+number.zfill(2)
        out.append(f'| {code} | [{cell(title)}](../04-演示简历与复习/04-综合面试追问.md#{code.lower()}) |')
    write(QA / '16-题目总索引.md', '\n'.join(out))


def main() -> None:
    source_navigation()
    schema_reference()
    api_reference()
    evidence_reference()
    question_index()
    # Snapshot records provenance only. Do not infer current test pass from hashes.
    for path in [legacy('docs/PROJECT_STATUS.md'), legacy('docs/AI_IMPLEMENTATION_SPEC.md'), legacy('docs/LEARNING_AND_INTERVIEW_GUIDE.md'), ROOT/'docs/baseline.lock.json']:
        INPUTS.add(path)
    snapshot = {
        'as_of': '2026-10-20', 'scope': 'M0-M7 final V8; documentation only; no business tests rerun',
        'source_files': [{'path': relative(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(INPUTS)],
    }
    write(STUDY / '资料快照.json', json.dumps(snapshot, ensure_ascii=False, indent=2))
    print(json.dumps({'generated': ['19','20','21','23','question-index','snapshot'], 'input_files': len(INPUTS)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
