package cn.iocoder.yudao.module.fulfillment.dal.dataobject;
import cn.iocoder.yudao.framework.tenant.core.db.TenantBaseDO;
import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import lombok.EqualsAndHashCode;
import java.math.BigDecimal;
import java.time.LocalDateTime;
@Data
@EqualsAndHashCode(callSuper=true)
@TableName("ful_stock_ledger")
public class FulStockLedgerDO extends TenantBaseDO {
    private String reason;
    @TableId(type=IdType.AUTO)
    private Long id;
    private Long reservationId;
    private Long warehouseId;
    private Long productId;
    private Long erpStockRecordId;
    private Long actorId;
    private String operationNo;
    private String eventType;
    private Integer lineNo;
    private BigDecimal heldDelta;
    private BigDecimal reservedAfter;
}
