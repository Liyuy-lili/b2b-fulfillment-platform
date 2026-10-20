package cn.iocoder.yudao.module.fulfillment.dal.mysql;

import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import cn.iocoder.yudao.module.fulfillment.dal.dataobject.FulCommandRecordDO;
import org.apache.ibatis.annotations.*;
import com.baomidou.mybatisplus.annotation.InterceptorIgnore;
import java.time.LocalDateTime;

@Mapper
public interface FulCommandRecordMapper extends BaseMapperX<FulCommandRecordDO> {
    // Duplicate insert waits for the first transaction. Failed commands roll back the row too.
    @InterceptorIgnore(tenantLine="true")
    @Insert("INSERT INTO ful_command_record (tenant_id,actor_id,command_type,idempotency_key,request_hash,creator,updater,create_time,update_time) VALUES (#{tenant},#{actor},#{type},#{key},#{hash},#{actor},#{actor},#{now},#{now}) ON DUPLICATE KEY UPDATE id=id")
    void ensure(@Param("type") String type, @Param("tenant") long tenant, @Param("actor") long actor, @Param("key") String key,
                @Param("hash") String hash, @Param("now") LocalDateTime now);

    @InterceptorIgnore(tenantLine="true")
    @Select("SELECT * FROM ful_command_record WHERE tenant_id=#{tenant} AND actor_id=#{actor} AND command_type=#{type} AND idempotency_key=#{key} AND deleted=0 FOR UPDATE")
    FulCommandRecordDO lock(@Param("type") String type, @Param("tenant") long tenant, @Param("actor") long actor, @Param("key") String key);
}
