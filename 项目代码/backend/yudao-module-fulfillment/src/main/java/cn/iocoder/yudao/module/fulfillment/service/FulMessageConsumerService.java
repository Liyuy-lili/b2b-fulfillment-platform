package cn.iocoder.yudao.module.fulfillment.service;
import cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder;
import cn.iocoder.yudao.module.fulfillment.framework.MessageProperties;
import cn.iocoder.yudao.module.fulfillment.domain.FulfillmentEvent;
import cn.iocoder.yudao.module.fulfillment.domain.FulfillmentEvent.Snapshot;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;
import java.util.*;
import static cn.iocoder.yudao.module.fulfillment.service.FulMessageStore.*;

@Service @RequiredArgsConstructor
public class FulMessageConsumerService {
    private final JdbcTemplate jdbc;private final FulMessageStore store;private final FulCommandService json;
    private final MessageProperties properties;private final ObjectProvider<FulMessageFault> faults;
    private void tenant(Trusted e){if(TenantContextHolder.getRequiredTenantId()!=e.tenant())throw new IllegalStateException("Trusted tenant context required");}
    private Map<String,Object> ensure(Trusted e){
        jdbc.update("INSERT INTO ful_inbox_event(tenant_id,event_id,consumer_name,next_attempt_at,created_at) VALUES(?,?,?,UTC_TIMESTAMP(6),UTC_TIMESTAMP(6)) ON DUPLICATE KEY UPDATE id=id",e.tenant(),e.event().eventId(),CONSUMER);
        return jdbc.queryForMap("SELECT *,next_attempt_at<=UTC_TIMESTAMP(6) AS due FROM ful_inbox_event WHERE tenant_id=? AND consumer_name=? AND event_id=? FOR UPDATE",e.tenant(),CONSUMER,e.event().eventId());
    }
    @Transactional(rollbackFor=Exception.class,isolation=Isolation.READ_COMMITTED,timeout=10)
    public String deliver(Trusted e,Long expectedVersion){
        tenant(e);var inbox=ensure(e);String status=text(inbox,"status");
        if(status.equals("PROCESSED")){
            jdbc.update("UPDATE ful_inbox_event SET duplicate_count=duplicate_count+1 WHERE tenant_id=? AND id=?",e.tenant(),number(inbox,"id"));return "DUPLICATE";
        }
        if(status.equals("DEAD")||!flag(inbox,"due")||expectedVersion!=null&&number(inbox,"version")!=expectedVersion)return "DEFERRED";
        var event=e.event();boolean applied=apply(e.tenant(),event.data(),event.eventId());
        faults.orderedStream().forEach(f->f.afterProjection(event.eventId()));
        jdbc.update("UPDATE ful_inbox_event SET status='PROCESSED',attempts=attempts+1,total_attempts=total_attempts+1,version=version+1,last_error=NULL,processed_at=UTC_TIMESTAMP(6),applied=? WHERE tenant_id=? AND id=?",applied,e.tenant(),number(inbox,"id"));
        return applied?"APPLIED":"OLDER_VERSION";
    }
    @Transactional(rollbackFor=Exception.class,isolation=Isolation.READ_COMMITTED,timeout=10)
    public void failed(Trusted e,Long expectedVersion,String error){
        tenant(e);var row=ensure(e);if(Set.of("PROCESSED","DEAD").contains(text(row,"status")))return;
        if(expectedVersion!=null&&number(row,"version")!=expectedVersion)return;
        if(text(row,"status").equals("RETRY_WAIT")&&!flag(row,"due"))return;
        int attempt=((Number)row.get("attempts")).intValue()+1;long delay=FulfillmentEvent.retryDelayMs(e.event().eventId(),attempt,properties.getRetryBaseMs());
        jdbc.update("UPDATE ful_inbox_event SET status=?,attempts=?,total_attempts=total_attempts+1,version=version+1,next_attempt_at=TIMESTAMPADD(MICROSECOND,?,UTC_TIMESTAMP(6)),last_error=? WHERE tenant_id=? AND id=?",attempt>=properties.getMaxAttempts()?"DEAD":"RETRY_WAIT",attempt,delay*1000,error,e.tenant(),number(row,"id"));
    }
    /** Ensure+row lock protects first creation and prevents older data overwriting rebuilds. */
    @Transactional(propagation=Propagation.MANDATORY)
    public boolean apply(long tenant,Snapshot snapshot,String eventId){
        return writeProjection(tenant,snapshot,eventId,false);
    }
    @Transactional(propagation=Propagation.MANDATORY)
    public boolean rebuild(long tenant,Snapshot snapshot){return writeProjection(tenant,snapshot,null,true);}
    private boolean writeProjection(long tenant,Snapshot snapshot,String eventId,boolean allowEqual){
        String body=json.canonical(snapshot);long version=Long.parseLong(snapshot.version()),order=Long.parseLong(snapshot.orderId());
        if(body.getBytes(java.nio.charset.StandardCharsets.UTF_8).length>262144)throw cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception(cn.iocoder.yudao.module.fulfillment.enums.FulfillmentErrors.MESSAGE_TOO_LARGE);
        jdbc.update("INSERT INTO ful_order_read_model(tenant_id,order_id,observed_version,source_event_id,snapshot_json,updated_at) VALUES(?,?,0,NULL,?,UTC_TIMESTAMP(6)) ON DUPLICATE KEY UPDATE id=id",tenant,order,"{}");
        var old=jdbc.queryForMap("SELECT observed_version,source_event_id,snapshot_json FROM ful_order_read_model WHERE tenant_id=? AND order_id=? FOR UPDATE",tenant,order);
        boolean empty="{}".equals(text(old,"snapshot_json"));
        if(number(old,"observed_version")>version||!empty&&!allowEqual&&number(old,"observed_version")==version)return false;
        jdbc.update("UPDATE ful_order_read_model SET observed_version=?,source_event_id=?,snapshot_json=?,updated_at=UTC_TIMESTAMP(6) WHERE tenant_id=? AND order_id=?",version,eventId,body,tenant,order);return true;
    }
}
