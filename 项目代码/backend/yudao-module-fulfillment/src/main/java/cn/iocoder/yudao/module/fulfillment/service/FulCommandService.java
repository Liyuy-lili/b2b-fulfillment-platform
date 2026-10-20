package cn.iocoder.yudao.module.fulfillment.service;

import cn.hutool.crypto.digest.DigestUtil;
import cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder;
import cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils;
import cn.iocoder.yudao.module.fulfillment.dal.dataobject.FulCommandRecordDO;
import cn.iocoder.yudao.module.fulfillment.dal.mysql.FulCommandRecordMapper;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import java.time.*;
import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;
import static cn.iocoder.yudao.module.fulfillment.enums.FulfillmentErrors.IDEMPOTENCY_KEY_CONFLICT;

@Service
@RequiredArgsConstructor
public class FulCommandService {
    private final FulCommandRecordMapper mapper;
    private final ObjectMapper json;
    public FulCommandRecordDO claim(String type,String key,String canonical) {
        return claim(type,key,canonical,SecurityFrameworkUtils.getLoginUserId());
    }
    // Java-only housekeeping entry. No fabricated login or privilege elevation.
    FulCommandRecordDO claimExpiry(long reservationId) {
        return claim("EXPIRE","reservation:"+reservationId,canonical(java.util.List.of("EXPIRE:v1",String.valueOf(reservationId))),0L);
    }
    private FulCommandRecordDO claim(String type,String key,String canonical,long actor) {
        long tenant=TenantContextHolder.getRequiredTenantId();
        String hash=DigestUtil.sha256Hex(canonical);
        mapper.ensure(type,tenant,actor,key,hash,LocalDateTime.now(ZoneOffset.UTC));
        var command=mapper.lock(type,tenant,actor,key);
        if(!command.getRequestHash().equals(hash)) throw exception(IDEMPOTENCY_KEY_CONFLICT);
        return command;
    }
    public String canonical(Object value) {
        try { return json.writeValueAsString(value); }
        catch(JsonProcessingException e) { throw new IllegalStateException(e); }
    }
    public <T> T replay(FulCommandRecordDO command,Class<T> type) {
        try { return json.readValue(command.getResponseJson(),type); }
        catch(JsonProcessingException e) { throw new IllegalStateException("Invalid saved command response",e); }
    }
    public <T> T complete(FulCommandRecordDO command,T result) {
        command.setResponseJson(canonical(result)).setResponseCode(0);
        command.setUpdateTime(LocalDateTime.now(ZoneOffset.UTC));
        mapper.updateById(command);
        return result;
    }
}
