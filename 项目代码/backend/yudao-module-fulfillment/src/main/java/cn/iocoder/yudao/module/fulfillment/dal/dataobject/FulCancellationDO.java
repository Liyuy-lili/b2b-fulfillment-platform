package cn.iocoder.yudao.module.fulfillment.dal.dataobject;
import cn.iocoder.yudao.framework.tenant.core.db.TenantBaseDO;
import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import lombok.EqualsAndHashCode;
import java.math.BigDecimal;
import java.time.LocalDateTime;
@Data @EqualsAndHashCode(callSuper=true) @TableName("ful_cancellation")
public class FulCancellationDO extends TenantBaseDO {
    @TableId(type=IdType.AUTO)
    private Long id;
    private Long orderId;
    private Long orderItemId;
    private Long actorId;
    private String operationNo;
    private String reason;
    private BigDecimal quantity;
}
