package cn.iocoder.yudao.module.fulfillment.dal.mysql;
import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import cn.iocoder.yudao.module.fulfillment.dal.dataobject.FulShipmentDO;
import org.apache.ibatis.annotations.Mapper;
@Mapper
public interface FulShipmentMapper extends BaseMapperX<FulShipmentDO> {

    @com.baomidou.mybatisplus.annotation.InterceptorIgnore(tenantLine="true")
    @org.apache.ibatis.annotations.Select("SELECT * FROM ful_shipment WHERE tenant_id=#{tenant} AND id=#{id} AND deleted=0 FOR UPDATE")
    FulShipmentDO lock(@org.apache.ibatis.annotations.Param("tenant") long tenant,@org.apache.ibatis.annotations.Param("id") long id);

}
