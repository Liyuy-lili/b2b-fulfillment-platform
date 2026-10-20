package cn.iocoder.yudao.module.fulfillment.dal.dataobject;
import cn.iocoder.yudao.framework.tenant.core.db.TenantBaseDO;
import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import lombok.EqualsAndHashCode;
import java.math.BigDecimal;
import java.time.LocalDateTime;
@Data @EqualsAndHashCode(callSuper=true) @TableName("ful_shipment")
public class FulShipmentDO extends TenantBaseDO {
    @TableId(type=IdType.AUTO)
    private Long id;
    private Long orderId;
    private Long warehouseId;
    private Long erpSaleOutId;
    private String shipmentNo;
    private String status;
    private String carrierCode;
    private String trackingNo;
    private LocalDateTime shippedAt;
    private LocalDateTime deliveredAt;
}
