package cn.iocoder.yudao.module.fulfillment.service;
import cn.hutool.crypto.digest.DigestUtil;
import cn.iocoder.yudao.module.fulfillment.domain.FulfillmentEvent;
import cn.iocoder.yudao.module.fulfillment.framework.MessageProperties;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;
import java.nio.charset.StandardCharsets;
import java.sql.Statement;
import java.util.*;

@Service @RequiredArgsConstructor
public class FulMessageStore {
    public static final String CONSUMER="fulfillment-order-view-v1";
    private final JdbcTemplate jdbc;private final MessageProperties properties;private final ObjectMapper json;
    public record Claim(long id,long tenant,String eventId,String body,long leaseVersion,String owner,int attempts) {}
    public record Trusted(long tenant,FulfillmentEvent event,String body) {}
    public static final class PoisonMessage extends RuntimeException {public PoisonMessage(){super("Untrusted or unsupported event envelope");}}
    public static long number(Map<String,Object> r,String key){return ((Number)r.get(key)).longValue();}
    public static String text(Map<String,Object> r,String key){return Objects.toString(r.get(key),null);}
    public static boolean flag(Map<String,Object> r,String key){Object v=r.get(key);return Boolean.TRUE.equals(v)||v instanceof Number n&&n.intValue()!=0;}
    public long insert(String sql,Object...args){
        var key=new GeneratedKeyHolder();jdbc.update(c->{var s=c.prepareStatement(sql,Statement.RETURN_GENERATED_KEYS);for(int i=0;i<args.length;i++)s.setObject(i+1,args[i]);return s;},key);return Objects.requireNonNull(key.getKey()).longValue();
    }
    @Transactional(rollbackFor=Exception.class,isolation=Isolation.READ_COMMITTED,timeout=5)
    public Claim claim(String owner){
        var list=jdbc.queryForList("SELECT * FROM ful_outbox_event WHERE status='IN_FLIGHT' AND lease_until<=UTC_TIMESTAMP(6) ORDER BY lease_until,id LIMIT 1 FOR UPDATE SKIP LOCKED");
        if(list.isEmpty())list=jdbc.queryForList("SELECT * FROM ful_outbox_event WHERE status IN ('NEW','RETRY_WAIT') AND next_attempt_at<=UTC_TIMESTAMP(6) ORDER BY next_attempt_at,id LIMIT 1 FOR UPDATE SKIP LOCKED");
        if(list.isEmpty())return null;
        var row=list.get(0);long tenant=number(row,"tenant_id"),id=number(row,"id"),version=number(row,"lease_version")+1;String event=text(row,"event_id");
        jdbc.update("UPDATE ful_outbox_delivery SET result='EXPIRED',finished_at=UTC_TIMESTAMP(6),error='LEASE_EXPIRED' WHERE tenant_id=? AND event_id=? AND lease_version=? AND result='STARTED'",tenant,event,version-1);
        int attempts=((Number)row.get("attempts")).intValue();
        if(attempts>=properties.getMaxAttempts()){
            jdbc.update("UPDATE ful_outbox_event SET status='DEAD',lease_owner=NULL,lease_until=NULL,last_error='ATTEMPTS_EXHAUSTED' WHERE tenant_id=? AND id=?",tenant,id);return null;
        }
        jdbc.update("UPDATE ful_outbox_event SET status='IN_FLIGHT',attempts=attempts+1,total_attempts=total_attempts+1,lease_owner=?,lease_version=?,lease_until=TIMESTAMPADD(SECOND,?,UTC_TIMESTAMP(6)) WHERE tenant_id=? AND id=?",owner,version,properties.getLeaseSeconds(),tenant,id);
        insert("INSERT INTO ful_outbox_delivery(tenant_id,event_id,lease_version,lease_owner,started_at) VALUES(?,?,?,?,UTC_TIMESTAMP(6))",tenant,event,version,owner);
        return new Claim(id,tenant,event,text(row,"body"),version,owner,attempts+1);
    }
    @Transactional(rollbackFor=Exception.class,isolation=Isolation.READ_COMMITTED,timeout=5)
    public boolean finish(Claim c,boolean accepted,String error){
        String state=accepted?"SENT":c.attempts()>=properties.getMaxAttempts()?"DEAD":"RETRY_WAIT";
        long delay=accepted?0:FulfillmentEvent.retryDelayMs(c.eventId(),c.attempts(),properties.getRetryBaseMs());
        int count=jdbc.update("UPDATE ful_outbox_event SET status=?,next_attempt_at=TIMESTAMPADD(MICROSECOND,?,UTC_TIMESTAMP(6)),lease_owner=NULL,lease_until=NULL,last_error=?,sent_at=IF(?='SENT',UTC_TIMESTAMP(6),sent_at) WHERE tenant_id=? AND id=? AND status='IN_FLIGHT' AND lease_version=? AND lease_owner=? AND lease_until>UTC_TIMESTAMP(6)",state,delay*1000,accepted?null:error,state,c.tenant(),c.id(),c.leaseVersion(),c.owner());
        jdbc.update("UPDATE ful_outbox_delivery SET result=?,error=?,finished_at=UTC_TIMESTAMP(6) WHERE tenant_id=? AND event_id=? AND lease_version=? AND lease_owner=?",count==0?"LATE":accepted?"ACKED":"FAILED",count==0?(accepted?"CONFIRMED_STALE":"FAILED_STALE"):error,c.tenant(),c.eventId(),c.leaseVersion(),c.owner());
        return count==1;
    }
    /** Only a server-owned Outbox row can select the processing tenant. */
    public Trusted trusted(byte[] body){
        try{
            if(body.length>262144)throw new PoisonMessage();
            String raw=new String(body,StandardCharsets.UTF_8);var tree=json.readTree(raw);String eventId=tree.path("eventId").asText();UUID.fromString(eventId);
            var rows=jdbc.queryForList("SELECT tenant_id,body_hash,body FROM ful_outbox_event WHERE event_id=?",eventId);
            if(rows.size()!=1||!DigestUtil.sha256Hex(raw).equals(text(rows.get(0),"body_hash")))throw new PoisonMessage();
            var event=json.readValue(raw,FulfillmentEvent.class);event.validate();long tenant=number(rows.get(0),"tenant_id");
            if(!String.valueOf(tenant).equals(event.tenantId()))throw new PoisonMessage();
            return new Trusted(tenant,event,raw);
        }catch(PoisonMessage e){throw e;}catch(Exception e){throw new PoisonMessage();}
    }
    public List<Map<String,Object>> retryCandidates(){return jdbc.queryForList("SELECT id,tenant_id,event_id,version FROM ful_inbox_event WHERE status='RETRY_WAIT' AND next_attempt_at<=UTC_TIMESTAMP(6) ORDER BY next_attempt_at,id LIMIT ?",properties.getBatchSize());}
    public Trusted byEvent(String event){var rows=jdbc.queryForList("SELECT body FROM ful_outbox_event WHERE event_id=?",event);if(rows.isEmpty())throw new PoisonMessage();return trusted(text(rows.get(0),"body").getBytes(StandardCharsets.UTF_8));}
}
