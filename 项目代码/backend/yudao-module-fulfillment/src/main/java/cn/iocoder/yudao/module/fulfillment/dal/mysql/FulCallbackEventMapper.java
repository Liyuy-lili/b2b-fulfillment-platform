package cn.iocoder.yudao.module.fulfillment.dal.mysql;
import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import cn.iocoder.yudao.module.fulfillment.dal.dataobject.FulCallbackEventDO;
import org.apache.ibatis.annotations.Mapper;
@Mapper
public interface FulCallbackEventMapper extends BaseMapperX<FulCallbackEventDO> {

    @com.baomidou.mybatisplus.annotation.InterceptorIgnore(tenantLine="true")
    @org.apache.ibatis.annotations.Insert("INSERT INTO ful_callback_event(provider,event_id,shipment_id,payload_hash,result,event_type,received_at,occurred_at,tenant_id,creator,create_time,updater,update_time) VALUES(#{provider},#{event},#{shipment},#{hash},'RECEIVED',#{type},#{now},#{occurred},#{tenant},'logistics',#{now},'logistics',#{now}) ON DUPLICATE KEY UPDATE id=id")
    void claim(@org.apache.ibatis.annotations.Param("tenant") long tenant,@org.apache.ibatis.annotations.Param("provider") String provider,@org.apache.ibatis.annotations.Param("event") String event,@org.apache.ibatis.annotations.Param("shipment") long shipment,@org.apache.ibatis.annotations.Param("hash") String hash,@org.apache.ibatis.annotations.Param("type") String type,@org.apache.ibatis.annotations.Param("occurred") java.time.LocalDateTime occurred,@org.apache.ibatis.annotations.Param("now") java.time.LocalDateTime now);
    @com.baomidou.mybatisplus.annotation.InterceptorIgnore(tenantLine="true")
    @org.apache.ibatis.annotations.Select("SELECT * FROM ful_callback_event WHERE tenant_id=#{tenant} AND provider=#{provider} AND event_id=#{event} AND deleted=0 FOR UPDATE")
    FulCallbackEventDO lock(@org.apache.ibatis.annotations.Param("tenant") long tenant,@org.apache.ibatis.annotations.Param("provider") String provider,@org.apache.ibatis.annotations.Param("event") String event);

}
