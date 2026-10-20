package cn.iocoder.yudao.module.fulfillment.service;
import cn.hutool.crypto.digest.DigestUtil;
import cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder;
import cn.iocoder.yudao.module.fulfillment.domain.FulfillmentEvent;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.UUID;
import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;
import static cn.iocoder.yudao.module.fulfillment.enums.FulfillmentErrors.MESSAGE_TOO_LARGE;
@Service @RequiredArgsConstructor
public class FulOutboxService {
    private final JdbcTemplate jdbc;private final FulMessageSnapshots snapshots;private final FulCommandService commands;
    private final ObjectProvider<FulMessageFault> faults;
    @Transactional(propagation=Propagation.MANDATORY)
    public void append(long order,FulfillmentEvent.Type type,long command){
        long tenant=TenantContextHolder.getRequiredTenantId();var snapshot=snapshots.current(tenant,order);
        var event=new FulfillmentEvent(UUID.randomUUID().toString(),String.valueOf(tenant),String.valueOf(order),snapshot.version(),type,1,Instant.now().toString(),UUID.randomUUID().toString(),snapshot);
        event.validate();String body=commands.canonical(event);
        if(body.getBytes(StandardCharsets.UTF_8).length>262144)throw exception(MESSAGE_TOO_LARGE);
        jdbc.update("INSERT INTO ful_outbox_event(event_id,tenant_id,order_id,aggregate_version,event_type,payload_version,command_id,body,body_hash,next_attempt_at,created_at) VALUES(?,?,?,?,?,1,?,?,?,UTC_TIMESTAMP(6),UTC_TIMESTAMP(6))",event.eventId(),tenant,order,Long.parseLong(event.aggregateVersion()),type.name(),command,body,DigestUtil.sha256Hex(body));
        faults.orderedStream().forEach(f->f.afterAppend(type.name()));
    }
}
