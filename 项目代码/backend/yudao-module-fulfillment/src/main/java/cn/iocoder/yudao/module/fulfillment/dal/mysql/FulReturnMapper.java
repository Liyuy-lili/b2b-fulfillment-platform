package cn.iocoder.yudao.module.fulfillment.dal.mysql;
import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import cn.iocoder.yudao.module.fulfillment.dal.dataobject.FulReturnDO;
import org.apache.ibatis.annotations.*;
import com.baomidou.mybatisplus.annotation.InterceptorIgnore;
@Mapper
public interface FulReturnMapper extends BaseMapperX<FulReturnDO> {
    @InterceptorIgnore(tenantLine="true")
    @Select("SELECT * FROM ful_return WHERE tenant_id=#{tenant} AND order_id=#{order} AND id=#{id} AND deleted=0 FOR UPDATE")
    FulReturnDO lock(@Param("tenant") long tenant,@Param("order") long order,@Param("id") long id);
}
