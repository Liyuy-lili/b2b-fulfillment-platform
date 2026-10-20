package cn.iocoder.yudao.module.fulfillment.dal.dataobject;
import cn.iocoder.yudao.framework.tenant.core.db.TenantBaseDO;
import com.baomidou.mybatisplus.annotation.*;
import lombok.*;
import java.time.LocalDateTime;
@Data @EqualsAndHashCode(callSuper=true) @TableName("ful_return")
public class FulReturnDO extends TenantBaseDO {
    @TableId(type=IdType.AUTO) private Long id;
    private String returnNo;
    private Long orderId;
    private Long shipmentId;
    private Long warehouseId;
    private String status;
    private String reason;
    private Long erpSaleReturnId;
    private LocalDateTime receivedAt;
    private Long receivedBy;
    private LocalDateTime rejectedAt;
    private Long rejectedBy;
    private String rejectionReason;
}
