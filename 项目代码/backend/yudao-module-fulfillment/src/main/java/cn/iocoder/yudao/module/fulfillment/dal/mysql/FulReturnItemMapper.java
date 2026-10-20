package cn.iocoder.yudao.module.fulfillment.dal.mysql;
import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import cn.iocoder.yudao.module.fulfillment.dal.dataobject.FulReturnItemDO;
import org.apache.ibatis.annotations.*;
import com.baomidou.mybatisplus.annotation.InterceptorIgnore;
import java.math.BigDecimal;
import java.util.List;
@Mapper
public interface FulReturnItemMapper extends BaseMapperX<FulReturnItemDO> {
    // Caller holds the source/order lock, serializing all application/receipt/rejection writers.
    @InterceptorIgnore(tenantLine="true")
    @Select("SELECT COALESCE(SUM(i.quantity),0) FROM ful_return_item i JOIN ful_return r ON r.id=i.return_id AND r.tenant_id=i.tenant_id WHERE i.tenant_id=#{tenant} AND i.shipment_item_id=#{item} AND i.deleted=0 AND r.deleted=0 AND r.status IN ('REQUESTED','RECEIVED')")
    BigDecimal committed(@Param("tenant") long tenant,@Param("item") long item);
    @InterceptorIgnore(tenantLine="true")
    @Select("SELECT * FROM ful_return_item WHERE tenant_id=#{tenant} AND return_id=#{id} AND deleted=0 ORDER BY id FOR UPDATE")
    List<FulReturnItemDO> lockItems(@Param("tenant") long tenant,@Param("id") long id);
}
