package cn.iocoder.yudao.module.fulfillment.dal.dataobject;

import cn.iocoder.yudao.framework.tenant.core.db.TenantBaseDO;
import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import lombok.EqualsAndHashCode;
import java.math.BigDecimal;

@Data
@EqualsAndHashCode(callSuper=true)
@TableName("ful_order")
public class FulOrderDO extends TenantBaseDO {
    @TableId(type=IdType.AUTO)
    private Long id;
    private Long erpOrderId;
    private Long customerId;
    private Long ownerUserId;
    private Long accountId;
    private Long saleUserId;
    private Long version;
    private String orderNo;
    private String status;
    private String allocationStrategy;
    private Integer strategyVersion;
    private Boolean allocationAttempted;
    private BigDecimal totalPrice;
    private BigDecimal discountPercent;
    private BigDecimal discountPrice;
    private BigDecimal depositPrice;
}
