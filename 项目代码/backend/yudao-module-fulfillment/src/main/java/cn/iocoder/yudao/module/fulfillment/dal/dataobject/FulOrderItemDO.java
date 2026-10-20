package cn.iocoder.yudao.module.fulfillment.dal.dataobject;

import cn.iocoder.yudao.framework.tenant.core.db.TenantBaseDO;
import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import lombok.EqualsAndHashCode;
import java.math.BigDecimal;

@Data
@EqualsAndHashCode(callSuper=true)
@TableName("ful_order_item")
public class FulOrderItemDO extends TenantBaseDO {
    @TableId(type=IdType.AUTO)
    private Long id;
    private Long orderId;
    private Long erpOrderItemId;
    private Long productId;
    private Long unitId;
    private BigDecimal priceSnapshot;
    private BigDecimal taxPercent;
    private BigDecimal taxPrice;
    private BigDecimal totalPrice;
    private BigDecimal orderedQty;
    private BigDecimal openQty;
    private BigDecimal reservedQty;
    private BigDecimal shippedQty;
    private BigDecimal cancelledQty;
    private BigDecimal returnedQty;
}
