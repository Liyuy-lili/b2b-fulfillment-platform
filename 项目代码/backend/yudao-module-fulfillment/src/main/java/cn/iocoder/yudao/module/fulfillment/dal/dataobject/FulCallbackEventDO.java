package cn.iocoder.yudao.module.fulfillment.dal.dataobject;
import cn.iocoder.yudao.framework.tenant.core.db.TenantBaseDO;
import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import lombok.EqualsAndHashCode;
import java.math.BigDecimal;
import java.time.LocalDateTime;
@Data @EqualsAndHashCode(callSuper=true) @TableName("ful_callback_event")
public class FulCallbackEventDO extends TenantBaseDO {
    @TableId(type=IdType.AUTO)
    private Long id;
    private Long shipmentId;
    private String provider;
    private String eventId;
    private String payloadHash;
    private String result;
    private String eventType;
    private String lastConflictHash;
    private Integer conflictCount;
    private LocalDateTime receivedAt;
    private LocalDateTime occurredAt;
}
