package cn.iocoder.yudao.module.fulfillment.service;

import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder;
import cn.iocoder.yudao.module.fulfillment.controller.admin.FileJobContracts.*;
import cn.iocoder.yudao.module.fulfillment.framework.FileJobProperties;
import lombok.RequiredArgsConstructor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;
import java.nio.file.Path;
import java.util.*;
import static cn.iocoder.yudao.module.fulfillment.service.JobValues.*;
import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;
import static cn.iocoder.yudao.module.fulfillment.enums.FulfillmentErrors.*;

@Service @RequiredArgsConstructor
public class FulFileJobAdmin {
    private final JdbcTemplate jdbc;private final FulJobStore store;private final FulPrivateFiles files;private final FulJobExport exports;
    private final FulJobAuthorization auth;private final FulWarehouseAccess warehouses;private final FulCommandService commands;
    private final FulOperationAudit audit;private final FileJobProperties properties;
    private long tenant(){return TenantContextHolder.getRequiredTenantId();}
    private Map<String,Object> owned(String id,boolean lock){
        auth.permit(auth.actor(),"fulfillment:job:query");
        var rows=jdbc.queryForList("SELECT * FROM ful_file_job WHERE tenant_id=? AND id=?"+(lock?" FOR UPDATE":""),tenant(),FulOrderService.parseId(id));
        if(rows.isEmpty()||number(rows.get(0),"actor_id")!=auth.actor()&&!warehouses.admin(auth.actor()))throw exception(JOB_NOT_ACCESSIBLE);return rows.get(0);
    }
    private void admission(){
        store.gate(0);store.gate(tenant());
        String active="status IN ('PENDING','RUNNING','RETRY_WAIT','CANCEL_REQUESTED')";
        if(jdbc.queryForObject("SELECT COUNT(*) FROM ful_file_job WHERE "+active,Long.class)>=properties.getGlobalPendingLimit()
                ||jdbc.queryForObject("SELECT COUNT(*) FROM ful_file_job WHERE tenant_id=? AND "+active,Long.class,tenant())>=properties.getTenantPendingLimit())throw exception(JOB_CAPACITY_EXCEEDED);
    }
    private JobResult saved(Map<String,Object> job,String outcome,String key){
        audit.add(tenant(),auth.actor(),"JOB_SUBMIT","JOB",text(job,"id"),key,"USER_SUBMISSION",Map.of(),Map.of("type",text(job,"job_type"),"dataset",text(job,"dataset"),"status","PENDING"));
        return new JobResult(text(job,"id"),outcome);
    }
    @Transactional(rollbackFor=Exception.class,isolation=Isolation.READ_COMMITTED,timeout=10)
    public JobResult submitImport(ImportRequest request,String key){
        auth.importPermission(auth.actor());var file=files.metadata(tenant(),request.fileId());
        if(number(file,"actor_id")!=auth.actor()||!text(file,"kind").equals("INPUT"))throw exception(FILE_INVALID);
        var command=commands.claim("JOB_IMPORT",key,commands.canonical(List.of("CSV:v1",request.sourceSystem(),text(file,"sha256"))));
        if(command.getResponseJson()!=null){var result=commands.replay(command,JobResult.class);auth.downloadCheck(owned(result.jobId(),false));return result;}
        admission();long id=insert(jdbc,"INSERT INTO ful_file_job(tenant_id,actor_id,job_type,dataset,source_system,input_file_id,scope_json,next_attempt_at,created_at) VALUES(?,?,'IMPORT','DRAFT',?,?,?,UTC_TIMESTAMP(6),UTC_TIMESTAMP(6))",tenant(),auth.actor(),request.sourceSystem(),request.fileId(),audit.json(new Scope(List.of(),auth.actor(),null,false)));
        var job=jdbc.queryForMap("SELECT * FROM ful_file_job WHERE tenant_id=? AND id=?",tenant(),id);
        return commands.complete(command,saved(job,"IMPORT_QUEUED",key));
    }
    @Transactional(rollbackFor=Exception.class,isolation=Isolation.READ_COMMITTED,timeout=10)
    public JobResult submitExport(ExportRequest request,String key){
        auth.permit(auth.actor(),"fulfillment:job:query");auth.permit(auth.actor(),"fulfillment:job:export");
        var ids=request.warehouseIds()==null?List.<String>of():request.warehouseIds().stream().map(FulOrderService::parseId).sorted().map(String::valueOf).toList();
        if(new HashSet<>(ids).size()!=ids.size())throw exception(WAREHOUSE_SCOPE_DENIED);
        var command=commands.claim("JOB_EXPORT",key,commands.canonical(List.of("XLSX:v1",request.dataset().name(),ids,Objects.toString(request.orderStatus(),""))));
        if(command.getResponseJson()!=null){var result=commands.replay(command,JobResult.class);auth.downloadCheck(owned(result.jobId(),false));return result;}
        var scope=auth.freeze(request);admission();long maximum=exports.maximum(request.dataset().name(),tenant());
        long id=insert(jdbc,"INSERT INTO ful_file_job(tenant_id,actor_id,job_type,dataset,scope_json,max_source_id,prepared,next_attempt_at,created_at) VALUES(?,?,'EXPORT',?,?,?,1,UTC_TIMESTAMP(6),UTC_TIMESTAMP(6))",tenant(),auth.actor(),request.dataset().name(),audit.json(scope),maximum);
        return commands.complete(command,saved(jdbc.queryForMap("SELECT * FROM ful_file_job WHERE tenant_id=? AND id=?",tenant(),id),"EXPORT_QUEUED",key));
    }
    @Transactional(rollbackFor=Exception.class,isolation=Isolation.READ_COMMITTED,timeout=10)
    public JobResult control(ControlRequest request,String key,boolean retry){
        auth.permit(auth.actor(),retry?"fulfillment:job:retry":"fulfillment:job:cancel");var hint=owned(request.jobId(),false);
        if(retry)auth.downloadCheck(hint);
        String type=retry?"JOB_RETRY":"JOB_CANCEL";var command=commands.claim(type,key,commands.canonical(List.of(type,request.jobId(),request.reason().trim())));
        if(command.getResponseJson()!=null)return commands.replay(command,JobResult.class);
        if(retry)admission();var row=owned(request.jobId(),true);String state=text(row,"status"),outcome;
        if(retry){
            if(!Set.of("FAILED","PARTIAL_FAILED").contains(state))throw exception(JOB_STATE_CONFLICT);
            jdbc.update("UPDATE ful_file_job_row SET status='PENDING',error_code=NULL,outcome=NULL,updated_at=UTC_TIMESTAMP(6) WHERE tenant_id=? AND job_id=? AND status='FAILED'",tenant(),number(row,"id"));
            jdbc.update("UPDATE ful_file_job SET status='PENDING',failed_rows=0,attempts=0,next_attempt_at=UTC_TIMESTAMP(6),lease_owner=NULL,lease_until=NULL,lease_version=lease_version+1,last_error=NULL,result_file_id=NULL,error_file_id=NULL,completed_at=NULL WHERE tenant_id=? AND id=?",tenant(),number(row,"id"));outcome="RETRY_QUEUED";
        }else{
            if(Set.of("SUCCEEDED","PARTIAL_FAILED","FAILED","CANCELLED").contains(state))throw exception(JOB_STATE_CONFLICT);
            boolean running=Set.of("RUNNING","CANCEL_REQUESTED").contains(state);outcome=running?"CANCEL_REQUESTED":"CANCELLED";
            if(running)jdbc.update("UPDATE ful_file_job SET status='CANCEL_REQUESTED' WHERE tenant_id=? AND id=?",tenant(),number(row,"id"));
            else jdbc.update("UPDATE ful_file_job SET status='CANCELLED',completed_at=UTC_TIMESTAMP(6) WHERE tenant_id=? AND id=?",tenant(),number(row,"id"));
        }
        audit.add(tenant(),auth.actor(),type,"JOB",request.jobId(),key,request.reason().trim(),Map.of("status",state),Map.of("outcome",outcome));return commands.complete(command,new JobResult(request.jobId(),outcome));
    }
    public JobView get(String id){return view(owned(id,false));}
    public PageResult<JobView> page(String status,int page,int size){
        auth.permit(auth.actor(),"fulfillment:job:query");String where=" WHERE tenant_id=?";var args=new ArrayList<Object>();args.add(tenant());
        if(!warehouses.admin(auth.actor())){where+=" AND actor_id=?";args.add(auth.actor());}if(status!=null){where+=" AND status=?";args.add(status);}
        long total=jdbc.queryForObject("SELECT COUNT(*) FROM ful_file_job"+where,Long.class,args.toArray());args.add(size);args.add((page-1L)*size);
        var rows=jdbc.queryForList("SELECT * FROM ful_file_job"+where+" ORDER BY id DESC LIMIT ? OFFSET ?",args.toArray());return new PageResult<>(rows.stream().map(this::view).toList(),total);
    }
    public PageResult<RowView> rows(String id,int page,int size){
        var job=owned(id,false);downloadPermission(job);long total=jdbc.queryForObject("SELECT COUNT(*) FROM ful_file_job_row WHERE tenant_id=? AND job_id=?",Long.class,tenant(),number(job,"id"));
        var rows=jdbc.queryForList("SELECT row_no,status,external_no,erp_order_id,outcome,error_code FROM ful_file_job_row WHERE tenant_id=? AND job_id=? ORDER BY row_no LIMIT ? OFFSET ?",tenant(),number(job,"id"),size,(page-1L)*size);
        return new PageResult<>(rows.stream().map(r->new RowView((int)number(r,"row_no"),text(r,"status"),text(r,"external_no"),text(r,"erp_order_id"),text(r,"outcome"),text(r,"error_code"))).toList(),total);
    }
    public PageResult<AuditView> audits(String id,int page,int size){owned(id,false);return auditPage("JOB",id,page,size);}
    public PageResult<AuditView> auditPage(String type,String id,int page,int size){
        String where=" WHERE tenant_id=? AND object_type=? AND object_id=?";long total=jdbc.queryForObject("SELECT COUNT(*) FROM ful_operation_audit"+where,Long.class,tenant(),type,id);
        var rows=jdbc.queryForList("SELECT * FROM ful_operation_audit"+where+" ORDER BY id DESC LIMIT ? OFFSET ?",tenant(),type,id,size,(page-1L)*size);
        return new PageResult<>(rows.stream().map(r->new AuditView(text(r,"id"),text(r,"actor_id"),text(r,"operation"),text(r,"object_type"),text(r,"object_id"),text(r,"reason"),text(r,"before_json"),text(r,"after_json"),text(r,"request_id"),time(r.get("created_at")))).toList(),total);
    }
    private void downloadPermission(Map<String,Object> job){
        auth.downloadCheck(job);if(number(job,"actor_id")!=auth.actor()){var caller=new HashMap<>(job);caller.put("actor_id",auth.actor());auth.downloadCheck(caller);}
    }
    public record Download(Path path,String name,String contentType,long bytes) {}
    @Transactional(rollbackFor=Exception.class,isolation=Isolation.READ_COMMITTED,timeout=20)
    public Download download(String id,String kind)throws Exception {
        var job=owned(id,false);downloadPermission(job);String column=switch(kind){case "INPUT"->"input_file_id";case "RESULT"->"result_file_id";case "ERROR"->"error_file_id";default->throw exception(FILE_INVALID);};
        String fileId=text(job,column);if(fileId==null)throw exception(FILE_INVALID);var meta=files.metadata(tenant(),fileId);var path=files.verified(meta);downloadPermission(job);
        audit.add(tenant(),auth.actor(),"FILE_DOWNLOAD","JOB",id,UUID.randomUUID().toString(),"AUTHORIZED_DOWNLOAD",Map.of(),Map.of("kind",kind,"fileId",fileId,"sha256",text(meta,"sha256")));
        return new Download(path,"fulfillment-"+id+"-"+kind.toLowerCase(Locale.ROOT)+(kind.equals("RESULT")?".xlsx":".csv"),kind.equals("RESULT")?"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":"text/csv;charset=UTF-8",number(meta,"byte_size"));
    }
    private JobView view(Map<String,Object> row){
        int total=(int)number(row,"total_rows"),success=(int)number(row,"success_rows"),failed=(int)number(row,"failed_rows");
        return new JobView(text(row,"id"),text(row,"actor_id"),text(row,"job_type"),text(row,"dataset"),text(row,"status"),text(row,"source_system"),total,success,failed,total-success-failed,flag(row,"prepared"),(int)number(row,"attempts"),(int)number(row,"total_attempts"),text(row,"source_cursor"),text(row,"lease_version"),text(row,"last_error"),row.get("input_file_id")!=null,row.get("result_file_id")!=null,row.get("error_file_id")!=null,time(row.get("created_at")),time(row.get("started_at")),time(row.get("completed_at")),time(row.get("lease_until")),text(row,"scope_json"));
    }
}
