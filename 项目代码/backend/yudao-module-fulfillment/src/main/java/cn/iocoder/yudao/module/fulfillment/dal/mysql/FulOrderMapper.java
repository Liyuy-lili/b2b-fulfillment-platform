package cn.iocoder.yudao.module.fulfillment.dal.mysql;

import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import cn.iocoder.yudao.module.fulfillment.dal.dataobject.FulOrderDO;
import org.apache.ibatis.annotations.*;
import com.baomidou.mybatisplus.annotation.InterceptorIgnore;

@Mapper
public interface FulOrderMapper extends BaseMapperX<FulOrderDO> {
    @InterceptorIgnore(tenantLine="true")
    @Select("SELECT * FROM ful_order WHERE tenant_id=#{tenant} AND id=#{id} AND deleted=0 FOR UPDATE")
    FulOrderDO lockById(@Param("tenant") long tenant,@Param("id") long id);
    @InterceptorIgnore(tenantLine="true")
    @Select("SELECT * FROM ful_order WHERE tenant_id=#{tenant} AND erp_order_id=#{source} AND deleted=0 FOR UPDATE")
    FulOrderDO lockBySource(@Param("tenant") long tenant, @Param("source") long source);

    // Historical usage includes deleted drafts. An order with any history cannot be taken over.
    @InterceptorIgnore(tenantLine="true")
    @Select("SELECT id FROM erp_sale_out WHERE tenant_id=#{tenant} AND order_id=#{source} ORDER BY id LIMIT 1 FOR UPDATE")
    Long findOutHistory(@Param("tenant") long tenant, @Param("source") long source);

    @InterceptorIgnore(tenantLine="true")
    @Select("SELECT id FROM erp_sale_return WHERE tenant_id=#{tenant} AND order_id=#{source} ORDER BY id LIMIT 1 FOR UPDATE")
    Long findReturnHistory(@Param("tenant") long tenant, @Param("source") long source);
}
