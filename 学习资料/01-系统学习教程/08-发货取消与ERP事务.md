# 08 部分发货、取消与ERP事务

> 最终集成（2026-10-20）：M5已把发货/取消执行事件Outbox纳入同一个RC事务，ERP故障时事件也回滚；M6复核OPERATE范围，原key不绕过撤权。当前验证见M7.2-core/returns。

入口：FulExecutionController，核心FulExecutionService.ship/cancel；[M3决策](../05-设计决策与复盘/ADR-012-M3-发货取消与物流集成.md)、[验收](../10-验收证据/M3-验收报告.md)。

## 1. 发货的业务边界

一次针对一个仓库，从该订单有效预占选择部分数量。请求items[].id是reservationId，不能传orderItemId冒充。检查正数、重复项、同租户/订单/仓库、q≤held，以及锁等待后的期限。

业务角色确认真实出库，系统同次建立发货事实并审核ERP出库；没有独立拣货草稿阶段。物流回调不再扣库存。

## 2. H/R如何共同变化

A仓H6/R6，发4：

```text
预占 held6→2，consumed0→4
库存 R6→2
订单 reserved10→6，shipped0→4
ERP审核出库 H6→2
建立shipment/item、ERP项映射、实物/预占流水关联
保存命令响应并提交
```

只在同一事务内先降低R，再调用ERP降低H；库存行锁一直持有，不存在把释放量先提交给别人的窗口。可用量仍0，剩余2仍被预占。

## 3. 唯一扣H路径

履约不直接changePhysical。它调用ERP声明的ErpManagedSaleOutPort.createAndApprove，由ERP实现从冻结源单生成商品、价格、税率和原订单项，复用审核与库存流水。

ERP内部实现要求MANDATORY：没有已有事务即失败；有事务则加入。不能把内部审核改为REQUIRES_NEW先独立提交，否则后续履约失败会留下真实出库。

源单→履约主/明细→预占→有序库存→本事务新建ERP单据。公共手工出库仍禁止托管源单，没有HTTP的managed=true或全局线程放行标志。

## 4. 要整体回滚哪些东西

ERP内部库存批次后抛异常，或ERP审核返回后履约再抛异常，都必须回滚H/R、ERP头/项/库存流水/源单累计、reservation、订单执行量、发货头项、预占流水、命令结果。

历史测试在独立fault profile注入两处错误。Redis生成单号可能留空号，MySQL事务不回滚Redis计数；空号不等于重复出库。具体证据：[审核内部故障](../10-验收证据/M3-erp-approval-failure.json)、[核心](../10-验收证据/M3-acceptance.json)。

## 5. 取消的精确顺序

先检查q≤open+reserved。优先从open取消，剩余按预占ID稳定顺序释放held；减少R/reserved，增加cancelled并保存逐项原因/操作者。H和shipped不变。

例如open2/reserved5，取消4：open2→0，reserved5→3，cancelled+4，R−2。只需释放2，不是4。原商业ordered不变，完整记录客户当初买了多少。

取消与发货共享订单锁；后取得锁的一方用最新数量重算。若发货已经提交，取消不能再取消那部分，必须走退货。

## 6. 状态与页面投影

ERP原“待出库”通常按商业数量和出库累计计算。托管订单还需考虑cancelled，否则发4取消6会一直显示还待发6。项目策略投影返回托管标志及open+reserved/cancelled，前端禁选手工出库。

发货签收只改shipment配送状态；订单PARTIALLY_CLOSED不会变成FULFILLED。退货同样不倒减gross shipped。

## 自测

发货超时后换key再点，状态校验可能仍允许再发未发部分，所以应保留原key。为什么业务唯一键不能全面替代命令幂等？同一订单允许多次合法发货，不能简单把orderId设成唯一发货键。
