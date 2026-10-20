package cn.iocoder.yudao.module.fulfillment.dal.dataobject;
import cn.iocoder.yudao.framework.tenant.core.db.TenantBaseDO;
import com.baomidou.mybatisplus.annotation.*;
import lombok.*;
import java.math.BigDecimal;
@Data @EqualsAndHashCode(callSuper=true) @TableName("ful_return_item")
public class FulReturnItemDO extends TenantBaseDO {
    @TableId(type=IdType.AUTO) private Long id;
    private Long returnId;
    private Long orderId;
    private Long shipmentId;
    private Long orderItemId;
    private Long shipmentItemId;
    private BigDecimal quantity;
    private Long erpSaleReturnItemId;
    private Long erpStockRecordId;
}
