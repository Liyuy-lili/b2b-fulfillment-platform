package cn.iocoder.yudao.module.fulfillment.dal.dataobject;
import cn.iocoder.yudao.framework.tenant.core.db.TenantBaseDO;
import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import lombok.EqualsAndHashCode;
import java.math.BigDecimal;
import java.time.LocalDateTime;
@Data @EqualsAndHashCode(callSuper=true) @TableName("ful_shipment_item")
public class FulShipmentItemDO extends TenantBaseDO {
    @TableId(type=IdType.AUTO)
    private Long id;
    private Long orderId;
    private Long shipmentId;
    private Long orderItemId;
    private Long reservationId;
    private Long erpSaleOutItemId;
    private BigDecimal quantity;
}
