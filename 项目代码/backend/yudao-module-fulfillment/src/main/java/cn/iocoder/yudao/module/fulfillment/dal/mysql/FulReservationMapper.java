package cn.iocoder.yudao.module.fulfillment.dal.mysql;
import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import cn.iocoder.yudao.module.fulfillment.dal.dataobject.FulReservationDO;
import org.apache.ibatis.annotations.Mapper;
@Mapper
public interface FulReservationMapper extends BaseMapperX<FulReservationDO> {

    // Only the internal scheduler calls this cross-tenant, nonlocking keyset scan.
    @com.baomidou.mybatisplus.annotation.InterceptorIgnore(tenantLine="true")
    @org.apache.ibatis.annotations.Select("SELECT * FROM ful_reservation WHERE active_flag=1 AND deleted=0 AND expire_at<=#{cutoff} AND (expire_at>#{afterTime} OR (expire_at=#{afterTime} AND id>#{afterId})) ORDER BY expire_at,id LIMIT #{limit}")
    java.util.List<FulReservationDO> scanExpired(@org.apache.ibatis.annotations.Param("cutoff") java.time.LocalDateTime cutoff,
        @org.apache.ibatis.annotations.Param("afterTime") java.time.LocalDateTime afterTime,
        @org.apache.ibatis.annotations.Param("afterId") long afterId,@org.apache.ibatis.annotations.Param("limit") int limit);

    @com.baomidou.mybatisplus.annotation.InterceptorIgnore(tenantLine="true")
    @org.apache.ibatis.annotations.Select("SELECT * FROM ful_reservation WHERE tenant_id=#{tenant} AND order_id=#{order} AND held_qty>0 AND deleted=0 ORDER BY id FOR UPDATE")
    java.util.List<FulReservationDO> lockActive(@org.apache.ibatis.annotations.Param("tenant") long tenant,@org.apache.ibatis.annotations.Param("order") long order);
}
