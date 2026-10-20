package cn.iocoder.yudao.module.fulfillment.dal.dataobject;

import cn.iocoder.yudao.framework.tenant.core.db.TenantBaseDO;
import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import lombok.EqualsAndHashCode;
import java.math.BigDecimal;

@Data
@EqualsAndHashCode(callSuper=true)
@TableName("ful_command_record")
public class FulCommandRecordDO extends TenantBaseDO {
    @TableId(type=IdType.AUTO)
    private Long id;
    private Long actorId;
    private String commandType;
    private String idempotencyKey;
    private String requestHash;
    private String responseJson;
    private Integer responseCode;
}
