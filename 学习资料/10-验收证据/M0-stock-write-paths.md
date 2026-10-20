# M0 库存写入调用清单

源码静态核对；不表示全部入口的并发测试已通过。M2 必须逐项改造与回归。

| 调用文件 | 位置 |
| --- | --- |
| [ErpPurchaseInServiceImpl.java](../../项目代码/backend/yudao-module-erp/src/main/java/cn/iocoder/yudao/module/erp/service/purchase/ErpPurchaseInServiceImpl.java) | 199 |
| [ErpPurchaseReturnServiceImpl.java](../../项目代码/backend/yudao-module-erp/src/main/java/cn/iocoder/yudao/module/erp/service/purchase/ErpPurchaseReturnServiceImpl.java) | 180 |
| [ErpSaleOutServiceImpl.java](../../项目代码/backend/yudao-module-erp/src/main/java/cn/iocoder/yudao/module/erp/service/sale/ErpSaleOutServiceImpl.java) | 192 |
| [ErpSaleReturnServiceImpl.java](../../项目代码/backend/yudao-module-erp/src/main/java/cn/iocoder/yudao/module/erp/service/sale/ErpSaleReturnServiceImpl.java) | 192 |
| [ErpStockCheckServiceImpl.java](../../项目代码/backend/yudao-module-erp/src/main/java/cn/iocoder/yudao/module/erp/service/stock/ErpStockCheckServiceImpl.java) | 138 |
| [ErpStockInServiceImpl.java](../../项目代码/backend/yudao-module-erp/src/main/java/cn/iocoder/yudao/module/erp/service/stock/ErpStockInServiceImpl.java) | 133 |
| [ErpStockMoveServiceImpl.java](../../项目代码/backend/yudao-module-erp/src/main/java/cn/iocoder/yudao/module/erp/service/stock/ErpStockMoveServiceImpl.java) | 131 |
| [ErpStockMoveServiceImpl.java](../../项目代码/backend/yudao-module-erp/src/main/java/cn/iocoder/yudao/module/erp/service/stock/ErpStockMoveServiceImpl.java) | 134 |
| [ErpStockOutServiceImpl.java](../../项目代码/backend/yudao-module-erp/src/main/java/cn/iocoder/yudao/module/erp/service/stock/ErpStockOutServiceImpl.java) | 134 |

公共链路：ErpStockRecordServiceImpl.createStockRecord → ErpStockServiceImpl.updateStockCountIncrement → ErpStockMapper.updateCountIncrement。

M0 已实际验证采购入库、销售出库、库存盘点及反审核；其它入出库、调拨、采购退货和销售退货目前仅完成代码入口定位。

当前风险：库存首次创建竞争、基于旧读值生成的流水余额，以及 SUM 经 double 的精度路径；按 M2 计划解决，不将 M0 顺序测试等同并发验证。
