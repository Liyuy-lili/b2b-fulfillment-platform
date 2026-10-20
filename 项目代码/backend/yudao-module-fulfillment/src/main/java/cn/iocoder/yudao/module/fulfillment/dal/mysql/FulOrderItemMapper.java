package cn.iocoder.yudao.module.fulfillment.dal.mysql;

import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import cn.iocoder.yudao.module.fulfillment.dal.dataobject.FulOrderItemDO;
import cn.iocoder.yudao.module.erp.dal.dataobject.sale.ErpSaleOrderItemDO;
import org.apache.ibatis.annotations.*;
import com.baomidou.mybatisplus.annotation.InterceptorIgnore;
import java.util.List;

@Mapper
public interface FulOrderItemMapper extends BaseMapperX<FulOrderItemDO> {
    @InterceptorIgnore(tenantLine="true")
    @Select("SELECT * FROM ful_order_item WHERE tenant_id=#{tenant} AND order_id=#{order} AND deleted=0 ORDER BY id FOR UPDATE")
    List<FulOrderItemDO> lockItems(@Param("tenant") long tenant,@Param("order") long order);
    @InterceptorIgnore(tenantLine="true")
    @Select("SELECT * FROM erp_sale_order_items WHERE tenant_id=#{tenant} AND order_id=#{source} AND deleted=0 ORDER BY id FOR UPDATE")
    List<ErpSaleOrderItemDO> lockSourceItems(@Param("tenant") long tenant, @Param("source") long source);
}
