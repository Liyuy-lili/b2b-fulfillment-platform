package cn.iocoder.yudao.module.fulfillment.dal.mysql;
import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import cn.iocoder.yudao.module.fulfillment.dal.dataobject.FulShipmentItemDO;
import org.apache.ibatis.annotations.Mapper;
@Mapper
public interface FulShipmentItemMapper extends BaseMapperX<FulShipmentItemDO> {
    @com.baomidou.mybatisplus.annotation.InterceptorIgnore(tenantLine="true")
    @org.apache.ibatis.annotations.Select("SELECT * FROM ful_shipment_item WHERE tenant_id=#{tenant} AND shipment_id=#{shipment} AND deleted=0 ORDER BY id FOR UPDATE")
    java.util.List<FulShipmentItemDO> lockItems(@org.apache.ibatis.annotations.Param("tenant") long tenant,@org.apache.ibatis.annotations.Param("shipment") long shipment);

}
