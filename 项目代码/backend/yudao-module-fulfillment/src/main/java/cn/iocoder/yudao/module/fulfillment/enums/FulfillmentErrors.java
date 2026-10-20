package cn.iocoder.yudao.module.fulfillment.enums;

import cn.iocoder.yudao.framework.common.exception.ErrorCode;

/** Dedicated 1-080-000-xxx range, checked against enabled upstream modules. */
public interface FulfillmentErrors {
    ErrorCode JOB_NOT_ACCESSIBLE = new ErrorCode(1_080_000_070,"JOB_NOT_ACCESSIBLE: 任务不存在或无权访问");
    ErrorCode JOB_CAPACITY_EXCEEDED = new ErrorCode(1_080_000_071,"JOB_CAPACITY_EXCEEDED: 待处理任务已达到容量上限，请稍后再试");
    ErrorCode JOB_STATE_CONFLICT = new ErrorCode(1_080_000_072,"JOB_STATE_CONFLICT: 当前任务状态不允许此操作");
    ErrorCode FILE_INVALID = new ErrorCode(1_080_000_073,"FILE_INVALID: 文件类型、大小、内容或归属不合法");
    ErrorCode JOB_PERMISSION_REVOKED = new ErrorCode(1_080_000_074,"JOB_PERMISSION_REVOKED: 当前权限不再覆盖任务冻结范围");
    ErrorCode WAREHOUSE_SCOPE_DENIED = new ErrorCode(1_080_000_075,"WAREHOUSE_SCOPE_DENIED: 请求仓库不在当前授权范围内");
    ErrorCode MESSAGE_TOO_LARGE = new ErrorCode(1_080_000_060,"MESSAGE_TOO_LARGE: 事件快照超过1000行或256KiB，业务事务已回滚");
    ErrorCode MESSAGE_NOT_ACCESSIBLE = new ErrorCode(1_080_000_061,"MESSAGE_NOT_ACCESSIBLE: 事件不存在或不属于当前订单");
    ErrorCode MESSAGE_STATE_CONFLICT = new ErrorCode(1_080_000_062,"MESSAGE_STATE_CONFLICT: 发布租约仍有效或消费状态不允许本次操作");
    ErrorCode RECONCILE_BUSY = new ErrorCode(1_080_000_052,"RECONCILE_BUSY: 本实例正在核对，请稍后重试原请求");
    ErrorCode RECONCILE_NOT_ACCESSIBLE = new ErrorCode(1_080_000_050,"RECONCILE_NOT_ACCESSIBLE: 核对报告或差异不存在、不属于本人或当前租户");
    ErrorCode RECONCILE_LIMIT_EXCEEDED = new ErrorCode(1_080_000_051,"RECONCILE_LIMIT_EXCEEDED: 超出本次完整扫描上限，未生成部分报告");
    ErrorCode SOURCE_ORDER_NOT_APPROVED = new ErrorCode(1_080_000_001, "SOURCE_ORDER_NOT_APPROVED: 只允许绑定已审核销售单");
    ErrorCode SOURCE_ORDER_ALREADY_USED = new ErrorCode(1_080_000_002, "SOURCE_ORDER_ALREADY_USED: 源单已有出库或退货记录，不能接管");
    ErrorCode ORDER_NOT_ACCESSIBLE = new ErrorCode(1_080_000_003, "ORDER_NOT_ACCESSIBLE: 订单不存在或无权操作");
    ErrorCode SOURCE_ORDER_INVALID = new ErrorCode(1_080_000_004, "SOURCE_ORDER_INVALID: 源单编号、明细数量或商业快照不合法");
    ErrorCode IDEMPOTENCY_KEY_CONFLICT = new ErrorCode(1_080_000_005, "IDEMPOTENCY_KEY_CONFLICT: 相同幂等键对应不同请求");
    ErrorCode WAREHOUSE_NOT_ACCESSIBLE = new ErrorCode(1_080_000_010,"WAREHOUSE_NOT_ACCESSIBLE: 仓库不存在、未启用或不属于当前租户");
    ErrorCode INVALID_COMMAND = new ErrorCode(1_080_000_011,"INVALID_COMMAND: 编号、重复行或数量不合法");
    ErrorCode RESERVATION_NOT_ACCESSIBLE = new ErrorCode(1_080_000_012,"RESERVATION_NOT_ACCESSIBLE: 预占不存在、不属于此订单或释放量超过持有量");
    ErrorCode STOCK_CONFLICT = new ErrorCode(1_080_000_013,"STOCK_CONFLICT: 库存汇总不一致，本次操作已回滚");
    ErrorCode RESERVATION_EXPIRED = new ErrorCode(1_080_000_020,"RESERVATION_EXPIRED: 预占已到期，请释放后重新分配");
    ErrorCode CANNOT_CANCEL = new ErrorCode(1_080_000_021,"CANNOT_CANCEL: 取消量超过尚未发货量");
    ErrorCode SHIPMENT_NOT_ACCESSIBLE = new ErrorCode(1_080_000_022,"SHIPMENT_NOT_ACCESSIBLE: 发货记录不存在或无权访问");
    ErrorCode CALLBACK_AUTH_INVALID = new ErrorCode(1_080_000_030,"CALLBACK_AUTH_INVALID: 集成、签名或时间戳不合法");
    ErrorCode CALLBACK_CONFLICT = new ErrorCode(1_080_000_031,"CALLBACK_CONFLICT: 相同事件编号的业务内容冲突");
    ErrorCode CALLBACK_SHIPMENT_UNKNOWN = new ErrorCode(1_080_000_032,"CALLBACK_SHIPMENT_UNKNOWN: 尚未找到发货单，可稍后重试");
    ErrorCode RETURN_NOT_ACCESSIBLE = new ErrorCode(1_080_000_040,"RETURN_NOT_ACCESSIBLE: 退货不存在或不属于当前订单");
    ErrorCode RETURN_QUANTITY_EXCEEDED = new ErrorCode(1_080_000_041,"RETURN_QUANTITY_EXCEEDED: 申请中和已收货数量之和超过原发货量");
    ErrorCode RETURN_STATE_CONFLICT = new ErrorCode(1_080_000_042,"RETURN_STATE_CONFLICT: 已收货和已拒绝是互斥终态");
}
