package cn.iocoder.yudao.module.fulfillment.dal.dataobject;
import cn.iocoder.yudao.framework.tenant.core.db.TenantBaseDO;
import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import lombok.EqualsAndHashCode;
import java.math.BigDecimal;
import java.time.LocalDateTime;
@Data
@EqualsAndHashCode(callSuper=true)
@TableName("ful_reservation")
public class FulReservationDO extends TenantBaseDO {
    @TableId(type=IdType.AUTO)
    private Long id;
    private Long orderId;
    private Long orderItemId;
    private Long productId;
    private Long warehouseId;
    private Long version;
    private String reservationNo;
    private Integer allocationRound;
    private BigDecimal allocatedQty;
    private BigDecimal heldQty;
    private BigDecimal consumedQty;
    private BigDecimal releasedQty;
    private Boolean activeFlag;
    private LocalDateTime expireAt;
}
