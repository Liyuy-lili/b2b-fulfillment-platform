# B2B 订单与多仓履约系统

面向 Java 后端秋招的综合项目。采用芋道 ERP 基座二次开发，重点实现库存预占、分仓履约、可靠异步处理和仓库数据权限。

## 目录与运行位置

本文件夹是代码工程根目录。运行下面命令前先进入“项目代码”；教程、面试、规范和验收原件都在同级[学习资料](../学习资料/README.md)。

## 当前状态

截至2026-10-20，M0—M7约定主线已完成：多仓履约、统一库存保护、到期/退货/核对、Outbox/Inbox、可恢复文件任务、仓库授权，以及最终产物回归、联合索引实测、独立交付和面试材料。见[M7完整验收](../学习资料/10-验收证据/M7-验收报告.md)、[最终文件核对](../学习资料/10-验收证据/M7-final-qa.json)和[学习入口](../学习资料/README.md)。同机正常重启与合成性能实验不等于生产HA；一份历史子报告覆盖例外在报告中明确披露。

## 两份主要文档

| 文档 | 用途 |
| --- | --- |
| [AI 实施技术规范](../学习资料/09-项目规范与进度/AI_IMPLEMENTATION_SPEC.md) | AI 开发时的约束、架构、数据模型、事务规则、接口、任务顺序和验收标准 |
| [项目理解与面试手册](../学习资料/00-项目总学习手册.md) | 你理解业务、阅读代码、掌握原理、复盘每一阶段和准备面试时使用 |

持续推进时先看 [项目进度与交接记录](../学习资料/09-项目规范与进度/PROJECT_STATUS.md)。AI 进入仓库后先读 [AGENTS.md](../AGENTS.md)。

## 完整学习与面试资料（统一入口）

所有学习正文现已集中到同级 **[学习资料](../学习资料/README.md)**，按2026-10-20最终M0—M7/V8逐章更新。

- [系统教程](../学习资料/01-系统学习教程/README.md)：32份含目录，覆盖全主线、源码、DDL/API、练习与证据。
- [面试问答](../学习资料/02-面试问答/README.md)：192道专题，另有40道综合追问；短答/展开/追问/易错/定位分层。
- [完整题目索引](../学习资料/02-面试问答/16-题目总索引.md)、[演示与简历](../学习资料/04-演示简历与复习/README.md)、[运行和实测](../学习资料/06-运行交付与证据/README.md)。
- [本轮资料检查](../学习资料/10-验收证据/DOC-learning-complete-20261020.json)：静态文件/链接/哈希和既有数字核对，不是新跑业务验收或压测。

旧路径保留兼容跳转，原阶段资料现存字节已归档到08历史ZIP；历史证据仍引用原件，不把早期“待做”当最终状态。

## 已选基座

- 后端：[YunaiV/ruoyi-vue-pro](https://github.com/YunaiV/ruoyi-vue-pro)，`master-jdk17` 分支，提交 `7c397bbfae3e768b26e3ee962c5aa7064e8d7c96`。
- 前端：[yudaocode/yudao-ui-admin-vue3](https://github.com/yudaocode/yudao-ui-admin-vue3)，`master` 分支，提交 `0af03a93b6b6300f878e28add69b1c7a9f09ec34`。
- 采用模块化单体，当前运行 system/infra/ERP/fulfillment；ERP 不反向依赖履约模块。
- 上游原始文件和许可证保留；源码差异见 [导入对比](../学习资料/10-验收证据/M0-import.json)，补齐的表结构是本项目工作，不是上游官方 ERP SQL。

## 现在怎样体验

本机访问：**http://127.0.0.1:15173**。租户：`芋道源码`；账号：`admin`；密码：`admin123`。仅用于本地演示。

从 ERP 系统 → 履约订单体验绑定、列表和详情；也可使用产品、采购、销售、库存基座功能。普通首页的天气、项目数是上游静态示例，不是项目实际指标。演示源单 `XSDD20261017000079` 已绑定为履约单 33。

详情内有分配预览、预占/发货、取消、物流工作台。M3 演示销售单 `XSDD20261018000189`（履约181）已完成“预占10→发4→取消6→签收”，最终订单部分关闭、发货已签收。物流使用本地模拟器，通过真实 HTTP 验签回调，不连接物流公司。

M3 并发与故障验收入口为 `./tests/m3_instances.ps1`，创建真实测试业务，最后自动停止 48082/48083 测试实例；故障 profile 不能用于日常运行。完整步骤见 M3 报告。

“退货与收货”标签页可选原发货、查询可退额度、申请、确认实际收货、拒绝并看ERP入库关联。M4.2演示源单 `XSDD20261019000010`（履约228）：发6/取消4后，实际退回2，shipped仍6、returned2，原仓H14→16；另一份1件申请已拒绝。没有自动退款或恢复发货额度。核心验收入口 `tests/m4_return_acceptance.py` 使用独立新库/Redis DB5，并自动停止自己创建的JVM。

ERP系统 → 库存与履约核对可执行全租户扫描、查看本人报告和记录差异说明。主库本次扫描2529条、0差异；相同key重放旧报告，新key重新观察。确认说明不代表已修复，不自动改业务事实。原理见M4.3讲解；独立库故意污染验收为 `tests/m4_reconcile_acceptance.py`，使用Redis DB6，主库不注入污染。

“消息与读模型”标签页可查询事件/投递/Inbox，按独立权限重新发布原事件、重试本地消费或重建读模型，并保存原因审计。M5演示销售单`XSDD20261019000011`（履约229）：五个事件完成，原发货事件重发两次、一个Inbox，业务H20/R0不变。正常Start-Local启动便携RabbitMQ并启用工作者；应用profile单独运行默认关闭传输、仍写Outbox。独立验收用独立schema/vhost、Redis DB7，不能混用主队列。详见M5讲解和验收；Broker已确认与消费成功分别显示，ACK也可能表示持久化失败重试已接管。

当前本机已启用自动到期：只释放剩余预占、转回待分配，实物库存与累计发货不变。默认每批50、最多4批、轮间5秒；设置 `FULFILLMENT_EXPIRY_ENABLED=false` 并重启可暂停扫描，发货仍拒绝过期预占。独立验收入口 `tests/m4_expiry_acceptance.py` 会新建独立库、使用Redis DB4与48082/48083，保留测试数据并停止自己创建的进程。复现与边界见M4.1报告。

```powershell
# 已配置过的本机：启动 / 停止前后端；数据库默认保持运行
./scripts/Start-Local.ps1
./scripts/Stop-Local.ps1
# 连依赖一起停止（不删除数据）
./scripts/Stop-Local.ps1 -Dependencies
```

## 从干净环境安装（Windows）

需要 PowerShell 7、JDK 17、Python 3.10+、Node >=20.19.0 和 npm。实测版本见 [版本锁](docs/baseline.lock.json)。下载和数据库文件都在被 Git 忽略的 `.local/`；不改系统 PATH，不操作现有 MySQL80 服务。

```powershell
./scripts/Bootstrap-Local.ps1
./scripts/Bootstrap-Messaging.ps1
./scripts/Start-Local.ps1 -DependenciesOnly
# 仅首次执行；数据库已存在会拒绝，不会自动清库
./scripts/Initialize-Database.ps1
./scripts/Build.ps1
# 显式接管刚初始化的 M0 结构；不能在已迁移库再次 baseline
./scripts/Migrate-Database.ps1 -Action baseline
./scripts/Migrate-Database.ps1 -Action migrate
./scripts/Start-Local.ps1
python -m pip install -r tests/requirements.txt
python tests/m1_acceptance.py
python tests/m1_locking.py
python tests/m0_smoke.py
```

`Build.ps1` 跳过上游单元测试，完成前后端打包。新增领域单测的独立运行命令和完整验收说明见 [M3 报告](../学习资料/10-验收证据/M3-验收报告.md)。回归脚本创建有唯一前缀的测试业务、账号和租户，不自动删除。

已有M0库升级时先停止应用、构建，再显式baseline/migrate；已有迁移历史只需migrate，不要再次baseline。升级前停用旧应用实例，迁移后统一使用新产物。本机已完成V6，日常启动自动validate/migrate，不自动baseline，V1—V6均不得修改。手工校验运行 `./scripts/Migrate-Database.ps1 -Action validate`；不自动清库或repair。业务连接默认READ COMMITTED、锁等待3秒，并在启动时校验实际值。

| 组件 | 本地地址 / 参数 |
| --- | --- |
| 前端 | `127.0.0.1:15173` |
| 后端 | `127.0.0.1:48080`，profile=`fulfillment` |
| MySQL | `127.0.0.1:33306/fulfillment`，应用账号 `fulfillment / fulfillment-dev` |
| Redis | `127.0.0.1:36379`，独立数据目录，AOF everysec + RDB；正常停止时保存，保留基座单号序列 |
| RabbitMQ / 管理 | `127.0.0.1:35672` / `127.0.0.1:35673`；本地账号 `fulfillment / fulfillment-mq-dev`；vhost=`fulfillment` |
| Erlang 项目端口 | 分布35674、EPMD35675，loopback；不安装Windows服务 |
| MySQL 项目 root | `local-root-dev`，仅本地依赖初始化使用 |
| 日志与 PID | `.local/`；数据库使用独立数据目录 |

上述密码都是可公开的本地演示默认值。新环境初始化前可修改脚本与对应配置；共享部署要重新配置账户、网络及依赖。

若误删 Redis 数据后出现“生成订单号失败”，先停止 ERP 写入，在当前项目数据库和 Redis 均运行时执行 `python scripts/repair_erp_sequences.py`，再恢复应用。该维护脚本只把当天单号计数器提高到已有 SQL 单据号上界，不清空或修改业务数据。Redis 应持续使用同一数据目录，不能将单号序列当作可随意丢弃的缓存。

## 容器依赖方案

`docker compose -f deploy/compose.yaml up -d` 可按配置启动数据库和 Redis；先停止占用相同端口的本地依赖。Compose 只挂载空卷首次初始化，不会在已存在卷上自动执行 SQL。镜像标签和 digest 已锁定；**当前机器没有 Docker，容器方案仅检查了 YAML 和来源摘要，尚未做运行验收**。

## 本阶段怎么学

先读 [M0：基座与库存调用链](../学习资料/03-阶段原理讲解/M0-基座与库存调用链.md)，再读 [M1：订单接管与并发保护](../学习资料/03-阶段原理讲解/M1-订单接管与并发保护.md)、[M2：预占释放与统一库存保护](../学习资料/03-阶段原理讲解/M2-预占释放与统一库存保护.md)、[M3：部分发货取消与物流闭环](../学习资料/03-阶段原理讲解/M3-部分发货取消与物流闭环.md)。大纲设计仍以两份主文档为准，真实完成度以进度与验收证据为准。

继续阅读 [M4.1：自动到期与重复任务](../学习资料/03-阶段原理讲解/M4.1-自动到期与重复任务.md)、[M4.2：退货额度与ERP入库](../学习资料/03-阶段原理讲解/M4.2-退货额度与ERP入库.md)。下一部分为M4.3库存/履约核对，只报告差异，不自动改写事实。


## M6文件与仓库演示

ERP系统 → 文件任务（`/erp/fulfillment-jobs`）：上传[合成CSV](../学习资料/10-验收证据/M6-demo-input.csv)，sourceSystem用`MAIN_M6_6236388c`；两条有效行会复用原两张草稿，数量0行保留错误。查看行结果、填原因重试、下载错误CSV；也可选择范围创建库存/订单/发货XLSX。每行只创建未审核草稿，不会自动审核/预占/扣库存。

ERP系统 → 仓库作业（`/erp/fulfillment-warehouse`）：范围库存、预占与发货专用视图；管理员可按用户/仓库授予或撤销READ/OPERATE并查看审计。合成仓库账号`M6WH0893a961 / admin123`，仅READ仓库`61`，不能查整单价格/其他仓库。该账号仅本机演示，无真实客户数据。

Start-Local默认启用文件工作者；独立运行profile默认关闭。私有文件按数据库放在`.local/fulfillment-files/`，不能只备份数据库而遗漏文件。V1—V7已执行且不可修改。独立验收从`tests/m6_foundation.py`开始，再运行核心/约束/混合工作者；主库升级脚本为一次性V6→V7，不要在当前V7主库重跑。详见[M6报告](../学习资料/10-验收证据/M6-验收报告.md)。


## M7.1独立交付包

[本机ZIP](.local/releases/fulfillment-20261020-092017.zip)（153.3 MiB）包含jar、生产前端、SQL、启停/固定演示脚本、来源许可证与哈希清单，不含活跃配置或数据。按[交付手册](../学习资料/06-运行交付与证据/独立交付运行手册.md)在新目录/新库运行，启动后执行`node ./bin/Seed-Demo.cjs ./config.local.json`。

实际在源码外新目录和独立schema/Redis DB9/vhost、48082/15174完成分仓→发货/取消→签收→退货、消息与文件流程及正常应用重启。演示编号见[M7.1-demo.json](../学习资料/10-验收证据/M7.1-demo.json)，[报告](../学习资料/10-验收证据/M7.1-验收报告.md)与[讲解](../学习资料/03-阶段原理讲解/M7.1-独立交付与固定演示.md)。验收应用已停止，历史验收时主项目15173继续运行；当前是否启动请按端口和页面核实。同主机复用外部依赖，没有新OS/跨机/性能结论，M7其余约定部分现也已完成，最终状态见上方M7总报告。
