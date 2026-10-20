package cn.iocoder.yudao.module.fulfillment.service;

import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils;
import cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder;
import cn.iocoder.yudao.module.fulfillment.controller.admin.ReconcileContracts.*;
import cn.iocoder.yudao.module.fulfillment.domain.ReconcileEngine;
import cn.iocoder.yudao.module.system.api.permission.PermissionApi;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;
import java.sql.*;
import java.time.*;
import java.util.*;
import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;
import static cn.iocoder.yudao.framework.common.exception.enums.GlobalErrorCodeConstants.FORBIDDEN;
import static cn.iocoder.yudao.module.fulfillment.enums.FulfillmentErrors.*;

@Service @RequiredArgsConstructor
public class FulReconcileService {
    private final JdbcTemplate jdbc;
    private final FulCommandService commands;
    private final PermissionApi permissions;
    private final ObjectMapper json;
    private final ObjectProvider<ReconcileSnapshotObserver> observer;
    private final FulReconcileSnapshotReader snapshotReader;
    private long tenant(){return TenantContextHolder.getRequiredTenantId();}
    private long actor(){return SecurityFrameworkUtils.getLoginUserId();}
    private void permit(String permission){if(!permissions.hasAnyPermissions(actor(),permission))throw exception(FORBIDDEN);}
    private void queryPermit(){permit("fulfillment:reconcile:query");}
    private static long id(String value){return FulOrderService.parseId(value);}
    private static String str(Object value){return value==null?null:value.toString();}
    private static long num(Map<String,Object> r,String k){return ((Number)r.get(k)).longValue();}
    private static String time(Object value){return (value instanceof Timestamp t?t.toLocalDateTime(): (LocalDateTime)value).toString()+"Z";}
    private long insert(String sql,Object...args){
        var holder=new GeneratedKeyHolder();
        jdbc.update(c->{var statement=c.prepareStatement(sql,Statement.RETURN_GENERATED_KEYS);for(int i=0;i<args.length;i++)statement.setObject(i+1,args[i]);return statement;},holder);
        return Objects.requireNonNull(holder.getKey()).longValue();
    }
    // Outer RC claims the command and atomically persists complete results.
    // A separate read-only RR transaction observes facts without business locks.
    @Transactional(rollbackFor=Exception.class,isolation=Isolation.READ_COMMITTED,timeout=20)
    public RunResult run(RunRequest request,String key){
        queryPermit();permit("fulfillment:reconcile:run");
        var command=commands.claim("RECONCILE",key,commands.canonical(List.of(ReconcileEngine.VERSION,request.scope().name())));
        if(command.getResponseJson()!=null){var saved=commands.replay(command,RunResult.class);owned(id(saved.id()),false);return saved;}
        var snapshot=snapshotReader.read(tenant());
        var findings=snapshot.findings();
        long run=insert("INSERT INTO ful_reconcile_run(tenant_id,actor_id,rule_version,scope,snapshot_at,finished_at,scanned_count,difference_count,table_counts_json) VALUES(?,?,?,?,?,UTC_TIMESTAMP(6),?,?,?)",tenant(),actor(),ReconcileEngine.VERSION,request.scope().name(),snapshot.at(),snapshot.scanned(),findings.size(),commands.canonical(snapshot.counts()));
        for(var f:findings)insert("INSERT INTO ful_reconcile_item(tenant_id,run_id,rule_code,object_type,object_id,order_id,product_id,warehouse_id,expected_value,actual_value,detail) VALUES(?,?,?,?,?,?,?,?,?,?,?)",tenant(),run,f.ruleCode(),f.objectType(),f.objectId(),f.orderId(),f.productId(),f.warehouseId(),f.expectedValue(),f.actualValue(),f.detail());
        observer.ifAvailable(ReconcileSnapshotObserver::afterPersist);
        return commands.complete(command,view(owned(run,false)));
    }
    private Map<String,Object> owned(long run,boolean lock){
        var rows=jdbc.queryForList("SELECT * FROM ful_reconcile_run WHERE tenant_id=? AND actor_id=? AND id=?"+(lock?" FOR UPDATE":""),tenant(),actor(),run);
        if(rows.isEmpty())throw exception(RECONCILE_NOT_ACCESSIBLE);return rows.get(0);
    }
    private RunResult view(Map<String,Object> row){
        try{return new RunResult(str(row.get("id")),str(row.get("rule_version")),str(row.get("scope")),time(row.get("snapshot_at")),time(row.get("finished_at")),((Number)row.get("scanned_count")).intValue(),((Number)row.get("difference_count")).intValue(),json.readValue(str(row.get("table_counts_json")),new TypeReference<Map<String,Integer>>(){}));}
        catch(com.fasterxml.jackson.core.JsonProcessingException e){throw new IllegalStateException("Invalid report counts",e);}
    }
    public RunResult get(String run){queryPermit();return view(owned(id(run),false));}
    public PageResult<RunResult> page(int page,int size){
        queryPermit();long total=jdbc.queryForObject("SELECT COUNT(*) FROM ful_reconcile_run WHERE tenant_id=? AND actor_id=?",Long.class,tenant(),actor());
        var rows=jdbc.queryForList("SELECT * FROM ful_reconcile_run WHERE tenant_id=? AND actor_id=? ORDER BY id DESC LIMIT ? OFFSET ?",tenant(),actor(),size,Math.multiplyExact((long)page-1,size));
        return new PageResult<>(rows.stream().map(this::view).toList(),total);
    }
    public PageResult<FindingView> items(String run,int page,int size,String rule,String status){
        queryPermit();long runId=id(run);owned(runId,false);
        String suffix=" WHERE tenant_id=? AND run_id=?";List<Object> params=new ArrayList<>(List.of(tenant(),runId));
        if(rule!=null){suffix+=" AND rule_code=?";params.add(rule);}
        if(status!=null){suffix+=" AND resolution_status=?";params.add(status);}
        long total=jdbc.queryForObject("SELECT COUNT(*) FROM ful_reconcile_item"+suffix,Long.class,params.toArray());
        var pageParams=new ArrayList<>(params);pageParams.add(size);pageParams.add(Math.multiplyExact((long)page-1,size));
        var rows=jdbc.queryForList("SELECT * FROM ful_reconcile_item"+suffix+" ORDER BY id LIMIT ? OFFSET ?",pageParams.toArray());
        return new PageResult<>(rows.stream().map(r->new FindingView(str(r.get("id")),str(r.get("run_id")),str(r.get("rule_code")),str(r.get("object_type")),str(r.get("object_id")),str(r.get("order_id")),str(r.get("product_id")),str(r.get("warehouse_id")),str(r.get("expected_value")),str(r.get("actual_value")),str(r.get("detail")),str(r.get("resolution_status")))).toList(),total);
    }
    @Transactional(rollbackFor=Exception.class,isolation=Isolation.READ_COMMITTED,timeout=10)
    public ReviewView review(ReviewRequest request,String key){
        queryPermit();permit("fulfillment:reconcile:review");long item=id(request.itemId());String note=request.note().trim();if(note.isEmpty())throw exception(INVALID_COMMAND);
        var command=commands.claim("RECONCILE_REVIEW",key,commands.canonical(List.of(ReconcileEngine.VERSION,String.valueOf(item),note)));
        var found=jdbc.queryForList("SELECT run_id FROM ful_reconcile_item WHERE tenant_id=? AND id=?",tenant(),item);
        if(found.isEmpty())throw exception(RECONCILE_NOT_ACCESSIBLE);
        long run=num(found.get(0),"run_id");owned(run,true);
        if(command.getResponseJson()!=null)return commands.replay(command,ReviewView.class);
        long review=insert("INSERT INTO ful_reconcile_review(tenant_id,run_id,item_id,actor_id,note,reviewed_at) VALUES(?,?,?,?,?,UTC_TIMESTAMP(6))",tenant(),run,item,actor(),note);
        jdbc.update("UPDATE ful_reconcile_item SET resolution_status='ACKNOWLEDGED' WHERE tenant_id=? AND run_id=? AND id=?",tenant(),run,item);
        var row=jdbc.queryForMap("SELECT * FROM ful_reconcile_review WHERE tenant_id=? AND id=?",tenant(),review);
        return commands.complete(command,reviewView(row));
    }
    private ReviewView reviewView(Map<String,Object> r){return new ReviewView(str(r.get("id")),str(r.get("item_id")),str(r.get("actor_id")),str(r.get("note")),time(r.get("reviewed_at")));}
    public PageResult<ReviewView> reviews(String run,String item,int page,int size){
        queryPermit();long runId=id(run),itemId=id(item);owned(runId,false);
        long total=jdbc.queryForObject("SELECT COUNT(*) FROM ful_reconcile_review WHERE tenant_id=? AND run_id=? AND item_id=?",Long.class,tenant(),runId,itemId);
        var rows=jdbc.queryForList("SELECT * FROM ful_reconcile_review WHERE tenant_id=? AND run_id=? AND item_id=? ORDER BY id DESC LIMIT ? OFFSET ?",tenant(),runId,itemId,size,Math.multiplyExact((long)page-1,size));
        return new PageResult<>(rows.stream().map(this::reviewView).toList(),total);
    }
}
