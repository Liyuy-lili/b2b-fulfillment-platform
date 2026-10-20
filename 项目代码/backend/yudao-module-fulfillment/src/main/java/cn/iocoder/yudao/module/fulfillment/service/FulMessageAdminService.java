package cn.iocoder.yudao.module.fulfillment.service;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils;
import cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder;
import cn.iocoder.yudao.module.fulfillment.controller.admin.MessageContracts.*;
import cn.iocoder.yudao.module.system.api.permission.PermissionApi;
import lombok.RequiredArgsConstructor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;
import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.util.*;
import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;
import static cn.iocoder.yudao.framework.common.exception.enums.GlobalErrorCodeConstants.FORBIDDEN;
import static cn.iocoder.yudao.module.fulfillment.enums.FulfillmentErrors.*;
import static cn.iocoder.yudao.module.fulfillment.service.FulMessageStore.*;
@Service @RequiredArgsConstructor
public class FulMessageAdminService {
    private final JdbcTemplate jdbc;private final FulMessageStore store;private final FulCommandService commands;
    private final FulOrderService orders;private final PermissionApi permissions;private final FulMessageSnapshots snapshots;private final FulMessageConsumerService consumer;
    private long tenant(){return TenantContextHolder.getRequiredTenantId();}
    private long actor(){return SecurityFrameworkUtils.getLoginUserId();}
    private void permit(String p){if(!permissions.hasAnyPermissions(actor(),p))throw exception(FORBIDDEN);}
    private Map<String,Object> owned(String order){
        permit("fulfillment:message:query");long id=FulOrderService.parseId(order);
        var rows=jdbc.queryForList("SELECT id,owner_user_id,version FROM ful_order WHERE tenant_id=? AND id=? AND deleted=0",tenant(),id);
        if(rows.isEmpty())throw exception(ORDER_NOT_ACCESSIBLE);orders.requireOwner(number(rows.get(0),"owner_user_id"));return rows.get(0);
    }
    private Map<String,Object> event(long order,String event,boolean lock){
        var rows=jdbc.queryForList("SELECT *,lease_until>UTC_TIMESTAMP(6) AS lease_live FROM ful_outbox_event WHERE tenant_id=? AND order_id=? AND event_id=?"+(lock?" FOR UPDATE":""),tenant(),order,event);
        if(rows.isEmpty())throw exception(MESSAGE_NOT_ACCESSIBLE);return rows.get(0);
    }
    private static String time(Object o){if(o==null)return null;return (o instanceof Timestamp t?t.toLocalDateTime():(LocalDateTime)o).toString()+"Z";}
    private EventView view(Map<String,Object> e,boolean body){
        var rows=jdbc.queryForList("SELECT * FROM ful_inbox_event WHERE tenant_id=? AND consumer_name=? AND event_id=?",tenant(),CONSUMER,text(e,"event_id"));InboxView inbox=null;
        if(!rows.isEmpty()){var i=rows.get(0);inbox=new InboxView(text(i,"id"),text(i,"status"),(int)number(i,"attempts"),(int)number(i,"total_attempts"),(int)number(i,"duplicate_count"),flag(i,"applied"),time(i.get("next_attempt_at")),time(i.get("processed_at")),text(i,"last_error"));}
        return new EventView(text(e,"id"),text(e,"event_id"),text(e,"order_id"),text(e,"aggregate_version"),text(e,"event_type"),(int)number(e,"payload_version"),text(e,"status"),(int)number(e,"attempts"),(int)number(e,"total_attempts"),text(e,"lease_version"),time(e.get("lease_until")),time(e.get("next_attempt_at")),text(e,"last_error"),time(e.get("created_at")),time(e.get("sent_at")),inbox,body?text(e,"body"):null);
    }
    public PageResult<EventView> page(String order,String status,int page,int size){
        long id=number(owned(order),"id");String where=" WHERE tenant_id=? AND order_id=?";List<Object> args=new ArrayList<>(List.of(tenant(),id));if(status!=null){where+=" AND status=?";args.add(status);}
        long total=jdbc.queryForObject("SELECT COUNT(*) FROM ful_outbox_event"+where,Long.class,args.toArray());args.add(size);args.add(((long)page-1)*size);
        var rows=jdbc.queryForList("SELECT * FROM ful_outbox_event"+where+" ORDER BY id DESC LIMIT ? OFFSET ?",args.toArray());return new PageResult<>(rows.stream().map(r->view(r,false)).toList(),total);
    }
    public EventView get(String order,String event){return view(event(number(owned(order),"id"),event,false),true);}
    public PageResult<DeliveryView> deliveries(String order,String event,int page,int size){
        long id=number(owned(order),"id");event(id,event,false);long total=jdbc.queryForObject("SELECT COUNT(*) FROM ful_outbox_delivery WHERE tenant_id=? AND event_id=?",Long.class,tenant(),event);
        var rows=jdbc.queryForList("SELECT * FROM ful_outbox_delivery WHERE tenant_id=? AND event_id=? ORDER BY id DESC LIMIT ? OFFSET ?",tenant(),event,size,((long)page-1)*size);
        return new PageResult<>(rows.stream().map(r->new DeliveryView(text(r,"id"),text(r,"lease_version"),text(r,"lease_owner"),text(r,"result"),text(r,"error"),time(r.get("started_at")),time(r.get("finished_at")))).toList(),total);
    }
    public PageResult<ActionView> actions(String order,int page,int size){
        long id=number(owned(order),"id");long total=jdbc.queryForObject("SELECT COUNT(*) FROM ful_message_action WHERE tenant_id=? AND order_id=?",Long.class,tenant(),id);
        var rows=jdbc.queryForList("SELECT * FROM ful_message_action WHERE tenant_id=? AND order_id=? ORDER BY id DESC LIMIT ? OFFSET ?",tenant(),id,size,((long)page-1)*size);
        return new PageResult<>(rows.stream().map(r->new ActionView(text(r,"id"),text(r,"event_id"),text(r,"actor_id"),text(r,"action"),text(r,"reason"),text(r,"outcome"),time(r.get("created_at")))).toList(),total);
    }
    public ProjectionView projection(String order){
        var h=owned(order);long id=number(h,"id");var rows=jdbc.queryForList("SELECT * FROM ful_order_read_model WHERE tenant_id=? AND order_id=?",tenant(),id);
        if(rows.isEmpty())return new ProjectionView(String.valueOf(id),text(h,"version"),null,null,null,null);
        var r=rows.get(0);return new ProjectionView(String.valueOf(id),text(h,"version"),text(r,"observed_version"),text(r,"source_event_id"),text(r,"snapshot_json"),time(r.get("updated_at")));
    }
    @Transactional(rollbackFor=Exception.class,isolation=Isolation.READ_COMMITTED,timeout=10)
    public ActionResult replay(ReplayRequest r,String key){
        permit("fulfillment:message:replay");var command=commands.claim("MESSAGE_REPLAY",key,commands.canonical(List.of("MESSAGE_REPLAY:v1",r.orderId(),r.eventId(),r.action().name(),r.reason().trim())));
        long order=number(owned(r.orderId()),"id");event(order,r.eventId(),false);
        if(command.getResponseJson()!=null)return commands.replay(command,ActionResult.class);
        String outcome;
        if(r.action()==ReplayAction.REPUBLISH){
            var e=event(order,r.eventId(),true);if(text(e,"status").equals("IN_FLIGHT")&&flag(e,"lease_live"))throw exception(MESSAGE_STATE_CONFLICT);
            jdbc.update("UPDATE ful_outbox_delivery SET result='EXPIRED',error='MANUAL_RECOVERY',finished_at=UTC_TIMESTAMP(6) WHERE tenant_id=? AND event_id=? AND result='STARTED'",tenant(),r.eventId());
            jdbc.update("UPDATE ful_outbox_event SET status='NEW',attempts=0,next_attempt_at=UTC_TIMESTAMP(6),lease_owner=NULL,lease_until=NULL,lease_version=lease_version+1,last_error=NULL,sent_at=NULL WHERE tenant_id=? AND event_id=?",tenant(),r.eventId());outcome="REPUBLISH_QUEUED";
        }else{
            // Lock Inbox only, avoiding outbox->inbox inversion with consumer FK checks.
            var rows=jdbc.queryForList("SELECT * FROM ful_inbox_event WHERE tenant_id=? AND consumer_name=? AND event_id=? FOR UPDATE",tenant(),CONSUMER,r.eventId());
            if(rows.isEmpty())throw exception(MESSAGE_STATE_CONFLICT);
            if(text(rows.get(0),"status").equals("PROCESSED"))outcome="ALREADY_PROCESSED";
            else{jdbc.update("UPDATE ful_inbox_event SET status='RETRY_WAIT',attempts=0,version=version+1,next_attempt_at=UTC_TIMESTAMP(6),last_error=NULL WHERE tenant_id=? AND consumer_name=? AND event_id=?",tenant(),CONSUMER,r.eventId());outcome="CONSUME_RETRY_QUEUED";}
        }
        return commands.complete(command,audit(order,r.eventId(),command.getId(),r.action().name(),r.reason().trim(),outcome));
    }
    @Transactional(rollbackFor=Exception.class,isolation=Isolation.READ_COMMITTED,timeout=15)
    public ActionResult rebuild(RebuildRequest r,String key){
        permit("fulfillment:message:rebuild");var command=commands.claim("MESSAGE_REBUILD",key,commands.canonical(List.of("MESSAGE_REBUILD:v1",r.orderId(),r.reason().trim())));long order=number(owned(r.orderId()),"id");
        if(command.getResponseJson()!=null)return commands.replay(command,ActionResult.class);
        var snapshot=snapshots.rebuildSnapshot(tenant(),order);boolean applied=consumer.rebuild(tenant(),snapshot);
        return commands.complete(command,audit(order,null,command.getId(),"REBUILD",r.reason().trim(),applied?"READ_MODEL_REBUILT":"NEWER_MODEL_RETAINED"));
    }
    private ActionResult audit(long order,String event,long command,String action,String reason,String outcome){
        long id=store.insert("INSERT INTO ful_message_action(tenant_id,order_id,event_id,command_id,actor_id,action,reason,outcome,created_at) VALUES(?,?,?,?,?,?,?,?,UTC_TIMESTAMP(6))",tenant(),order,event,command,actor(),action,reason,outcome);return new ActionResult(String.valueOf(id),event,action,outcome);
    }
}
