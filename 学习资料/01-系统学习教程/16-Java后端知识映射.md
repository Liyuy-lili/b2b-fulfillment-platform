# 16 Java后端基础在本项目中的位置

> 最终集成（2026-10-20）：完整后半程还包含Semaphore准入、SKIP LOCKED、JDBC租约CAS、ThreadPoolExecutor拒绝策略、ThreadLocal恢复、UTF-8流和FastExcel，均可在25—29找到具体代码。

这章是学习索引，不声称实现了对应技术的全部底层功能。通用精度规则可参考 [JDK17 BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html)。

## 1. Java语言

| 概念 | 实际代码 | 要能解释的问题 |
| --- | --- | --- |
| 接口与实现 | ErpManagedOrderPolicy、出库/退货Port | 为什么声明在ERP而由不同模块实现/调用 |
| record | AllocationPlanner.Demand/Supply/Piece、请求契约 | 为什么适合不可变输入输出，不等于深层对象全不可变 |
| 泛型Supplier | DatabaseCommandRetry.run | 怎样复用返回类型不同的整命令调用 |
| 集合Map/Set | remaining、TreeMap数量、重复项校验 | 业务身份为何是复合键，排序为何稳定 |
| Stream | 键去重/排序、数量映射 | 哪些只是构造数据，真正副作用在哪里 |
| BigDecimal | 数量校验、计划、SQL汇总 | double误差、scale、precision、比较 |
| 异常 | 业务异常、悲观锁失败、CandidateNotDueException | 哪些返回业务错误，哪些回滚/重试 |
| 时间API | Instant、OffsetDateTime、UTC LocalDateTime | 事件时刻与本地展示如何换算 |

BigDecimal判断数值大小用compareTo；equals还区分scale，所以2.0与2.00可能equals为false。new BigDecimal("0.1")从十进制字符建立值；若先转double再构造，就可能已带来误差。当前业务校验还需限制正数/范围/有效小数，不是只换类型就足够。

## 2. Spring与工程

构造器注入让依赖可见；@Service注册业务Bean；@Transactional由代理建立事务，不能只凭注解存在认定调用经过代理；@PreAuthorize保护入口；@Validated/@Valid/@Pattern保护格式，跨表业务仍在Service检查。

AOP的实际用途是让ERP旧事务服务在最外层获得有限重试。理解顺序比背“切面能解耦”更重要：重试必须包住事务创建/失败回滚，不能反过来让三次尝试共享一个坏事务。

## 3. MyBatis与SQL

DO映射事实，Contracts面向接口；DO不能直接当万能HTTP输入。Mapper中的tenant_id、deleted、FOR UPDATE和条件表达式都是可审查业务约束。BaseMapperX用于复用常规查询，复杂锁操作用明确SQL。

批次锁先收齐全部键，再逐条更新；这与“把所有写入改成一个超大SQL”不是同一概念。集合排序不能替代SQL真正拿锁。

## 4. 并发知识

synchronized只协调同一JVM对象；项目双JVM共库必须靠数据库约束和锁。ThreadLocal承载租户/安全上下文，但线程复用要求finally恢复，普通线程池也不会自动携带完整事务。

到期调度单线程不等于全系统只有一个执行者；另一个实例也可扫同候选，幂等/锁仍必要。这里没有以ConcurrentHashMap保存库存余额来解决持久化竞争。

## 5. Web与安全

HTTP状态和CommonResult业务code需一起看；幂等key是业务协议，不是TCP自动重试。HMAC绑定secret与请求字节，SHA-256请求摘要只比较内容，不负责身份认证。认证、授权、对象归属、输入校验必须分别解释。

## 6. 设计模式的准确说法

- 分仓是纯计算、按策略枚举分支选择，属于可替换策略思想；当前不必夸称复杂插件式策略框架。
- ERP Port隔离调用与基座实现，是适配边界；不代表新增远程微服务。
- 状态计算集中到一个函数，避免多个入口重复判断；未引入专用状态机框架。
- 持久化命令记录把重复效果与原响应关联；不是缓存注解就能提供幂等。

## 7. 暂不应该认领的基础题

当前已有M5可靠消息、M6有界线程池/持久化任务、M7索引对比和CPU/堆/GC观测，分别读26/27/29。没有实现分库分表，也没有GC专项调优或生产容量证据；资源观测不能夸称完成JVM调优。

自测：给一个具体方法，分别找出输入格式、业务规则、数据库保护和错误处理。能做到这一步，比背几十个框架名更能说明掌握。
