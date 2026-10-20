package cn.iocoder.yudao.module.fulfillment.service;

import cn.iocoder.yudao.module.fulfillment.framework.FileJobProperties;
import lombok.RequiredArgsConstructor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;
import java.util.*;
import static cn.iocoder.yudao.module.fulfillment.service.JobValues.*;

@Service @RequiredArgsConstructor
public class FulJobStore {
    private final JdbcTemplate jdbc;private final FileJobProperties properties;
    private final FulOperationAudit audit;private final FulPrivateFiles files;
    public record Lease(Map<String,Object> job,String owner,long version){public long id(){return number(job,"id");}public long tenant(){return number(job,"tenant_id");}}
    public record InputRow(int no,String raw,String external,String error) {}
    public List<Long> candidates(int limit){return jdbc.queryForList("SELECT id FROM ful_file_job WHERE (status IN ('PENDING','RETRY_WAIT') AND next_attempt_at<=UTC_TIMESTAMP(6)) OR (status IN ('RUNNING','CANCEL_REQUESTED') AND lease_until<=UTC_TIMESTAMP(6)) ORDER BY id LIMIT ?",Long.class,limit);}
    public void gate(long tenant){
        jdbc.update("INSERT IGNORE INTO ful_job_gate(tenant_id) VALUES(?)",tenant);
        jdbc.queryForObject("SELECT tenant_id FROM ful_job_gate WHERE tenant_id=? FOR UPDATE",Long.class,tenant);
    }
    @Transactional(rollbackFor=Exception.class,isolation=Isolation.READ_COMMITTED,timeout=10)
    public Lease claim(long id,String owner){
        var hints=jdbc.queryForList("SELECT tenant_id FROM ful_file_job WHERE id=?",id);if(hints.isEmpty())return null;long tenant=number(hints.get(0),"tenant_id");gate(tenant);
        var rows=jdbc.queryForList("SELECT *,lease_until<=UTC_TIMESTAMP(6) AS expired,next_attempt_at<=UTC_TIMESTAMP(6) AS due FROM ful_file_job WHERE tenant_id=? AND id=? FOR UPDATE SKIP LOCKED",tenant,id);if(rows.isEmpty())return null;
        var row=rows.get(0);String state=text(row,"status");
        if(!(Set.of("PENDING","RETRY_WAIT").contains(state)&&flag(row,"due")||Set.of("RUNNING","CANCEL_REQUESTED").contains(state)&&flag(row,"expired")))return null;
        if(number(row,"attempts")>=properties.getMaxAttempts()&&!state.equals("CANCEL_REQUESTED")){
            terminal(row,"FAILED","ATTEMPT_LIMIT",owner);return null;
        }
        if(jdbc.queryForObject("SELECT COUNT(*) FROM ful_file_job WHERE tenant_id=? AND status IN ('RUNNING','CANCEL_REQUESTED') AND lease_until>UTC_TIMESTAMP(6)",Long.class,tenant)>=properties.getTenantConcurrency())return null;
        jdbc.update("UPDATE ful_file_job SET status=?,lease_owner=?,lease_until=TIMESTAMPADD(SECOND,?,UTC_TIMESTAMP(6)),lease_version=lease_version+1,attempts=attempts+1,total_attempts=total_attempts+1,started_at=UTC_TIMESTAMP(6),completed_at=NULL,last_error=NULL,source_cursor=IF(job_type='EXPORT',0,source_cursor),total_rows=IF(job_type='EXPORT',0,total_rows),success_rows=IF(job_type='EXPORT',0,success_rows),failed_rows=IF(job_type='EXPORT',0,failed_rows) WHERE tenant_id=? AND id=?",
                state.equals("CANCEL_REQUESTED")?"CANCEL_REQUESTED":"RUNNING",owner,properties.getLeaseSeconds(),tenant,id);
        var current=jdbc.queryForMap("SELECT * FROM ful_file_job WHERE tenant_id=? AND id=?",tenant,id);
        audit.add(tenant,number(row,"actor_id"),"JOB_CLAIM","JOB",String.valueOf(id),owner,"SCHEDULED",Map.of("status",state),Map.of("leaseVersion",number(current,"lease_version"),"owner",owner));
        return new Lease(current,owner,number(current,"lease_version"));
    }
    /** Called inside every mutating chunk/row transaction, including its final fence. */
    public Map<String,Object> lock(Lease lease,boolean allowCancel){
        var rows=jdbc.queryForList("SELECT *,lease_until>UTC_TIMESTAMP(6) AS live FROM ful_file_job WHERE tenant_id=? AND id=? FOR UPDATE",lease.tenant(),lease.id());
        if(rows.isEmpty())throw new LostLease();var row=rows.get(0);String state=text(row,"status");
        if(!lease.owner().equals(text(row,"lease_owner"))||number(row,"lease_version")!=lease.version()||!flag(row,"live")||!Set.of("RUNNING","CANCEL_REQUESTED").contains(state))throw new LostLease();
        if(state.equals("CANCEL_REQUESTED")&&!allowCancel)throw new Cancelled();return row;
    }
    @Transactional(rollbackFor=Exception.class,isolation=Isolation.READ_COMMITTED,timeout=5)
    public void renew(Lease lease){
        lock(lease,false);jdbc.update("UPDATE ful_file_job SET lease_until=TIMESTAMPADD(SECOND,?,UTC_TIMESTAMP(6)) WHERE tenant_id=? AND id=?",properties.getLeaseSeconds(),lease.tenant(),lease.id());
    }
    @Transactional(rollbackFor=Exception.class,isolation=Isolation.READ_COMMITTED,timeout=10)
    public void appendRows(Lease lease,List<InputRow> rows){
        var job=lock(lease,false);int cursor=(int)number(job,"parse_cursor"),errors=0;
        for(var row:rows){
            if(row.no()<=cursor)continue;
            jdbc.update("INSERT INTO ful_file_job_row(tenant_id,job_id,row_no,raw_json,status,external_no,error_code,updated_at) VALUES(?,?,?,?,?,?,?,UTC_TIMESTAMP(6))",lease.tenant(),lease.id(),row.no(),row.raw(),row.error()==null?"PENDING":"FAILED",row.external(),row.error());
            cursor=row.no();if(row.error()!=null)errors++;
        }
        lock(lease,false);jdbc.update("UPDATE ful_file_job SET parse_cursor=?,total_rows=?,failed_rows=failed_rows+? WHERE tenant_id=? AND id=?",cursor,cursor,errors,lease.tenant(),lease.id());
    }
    @Transactional(rollbackFor=Exception.class,isolation=Isolation.READ_COMMITTED,timeout=5)
    public void prepared(Lease lease){lock(lease,false);jdbc.update("UPDATE ful_file_job SET prepared=1 WHERE tenant_id=? AND id=?",lease.tenant(),lease.id());}
    public List<Map<String,Object>> pendingRows(Lease lease){return jdbc.queryForList("SELECT * FROM ful_file_job_row WHERE tenant_id=? AND job_id=? AND status='PENDING' ORDER BY row_no LIMIT ?",lease.tenant(),lease.id(),properties.getBatchSize());}
    @Transactional(rollbackFor=Exception.class,isolation=Isolation.READ_COMMITTED,timeout=10)
    public void rowFailed(Lease lease,int no,String error){
        lock(lease,false);int changed=jdbc.update("UPDATE ful_file_job_row SET status='FAILED',error_code=?,outcome='REJECTED',updated_at=UTC_TIMESTAMP(6) WHERE tenant_id=? AND job_id=? AND row_no=? AND status='PENDING'",error,lease.tenant(),lease.id(),no);
        lock(lease,false);if(changed==1)jdbc.update("UPDATE ful_file_job SET failed_rows=failed_rows+1 WHERE tenant_id=? AND id=?",lease.tenant(),lease.id());
    }
    @Transactional(rollbackFor=Exception.class,isolation=Isolation.READ_COMMITTED,timeout=10)
    public void exportProgress(Lease lease,long cursor,int total){
        lock(lease,false);jdbc.update("UPDATE ful_file_job SET source_cursor=?,total_rows=?,success_rows=? WHERE tenant_id=? AND id=?",cursor,total,total,lease.tenant(),lease.id());
    }
    @Transactional(rollbackFor=Exception.class,isolation=Isolation.READ_COMMITTED,timeout=10)
    public void finish(Lease lease,FulPrivateFiles.Sealed result,FulPrivateFiles.Sealed errors){
        var row=lock(lease,false);
        if(result!=null)files.register(result,lease.tenant(),number(row,"actor_id"));if(errors!=null)files.register(errors,lease.tenant(),number(row,"actor_id"));
        lock(lease,false);
        jdbc.update("UPDATE ful_file_job SET result_file_id=?,error_file_id=? WHERE tenant_id=? AND id=?",result==null?null:result.id(),errors==null?null:errors.id(),lease.tenant(),lease.id());
        terminal(row,number(row,"failed_rows")>0?"PARTIAL_FAILED":"SUCCEEDED",null,lease.owner());
    }
    @Transactional(rollbackFor=Exception.class,isolation=Isolation.READ_COMMITTED,timeout=10)
    public void failure(Lease lease,String error,boolean permanent){
        var row=lock(lease,true);if(text(row,"status").equals("CANCEL_REQUESTED")){terminal(row,"CANCELLED",null,lease.owner());return;}
        boolean last=permanent||number(row,"attempts")>=properties.getMaxAttempts();
        jdbc.update("UPDATE ful_file_job SET status=?,lease_owner=NULL,lease_until=NULL,last_error=?,next_attempt_at=TIMESTAMPADD(SECOND,?,UTC_TIMESTAMP(6)),completed_at=IF(?,UTC_TIMESTAMP(6),NULL) WHERE tenant_id=? AND id=?",last?"FAILED":"RETRY_WAIT",error,Math.min(60,1L<<Math.min(6,number(row,"attempts"))),last,lease.tenant(),lease.id());
        audit.add(lease.tenant(),number(row,"actor_id"),"JOB_FAILURE","JOB",String.valueOf(lease.id()),lease.owner(),error,Map.of("status",text(row,"status")),Map.of("status",last?"FAILED":"RETRY_WAIT"));
    }
    @Transactional(rollbackFor=Exception.class,isolation=Isolation.READ_COMMITTED,timeout=5)
    public void cancelled(Lease lease){var row=lock(lease,true);terminal(row,"CANCELLED",null,lease.owner());}
    private void terminal(Map<String,Object> row,String state,String error,String request){
        jdbc.update("UPDATE ful_file_job SET status=?,lease_owner=NULL,lease_until=NULL,last_error=?,completed_at=UTC_TIMESTAMP(6) WHERE tenant_id=? AND id=?",state,error,number(row,"tenant_id"),number(row,"id"));
        audit.add(number(row,"tenant_id"),number(row,"actor_id"),"JOB_"+state,"JOB",text(row,"id"),request,"WORKER_COMPLETION",Map.of("status",text(row,"status")),Map.of("status",state,"successRows",number(row,"success_rows"),"failedRows",number(row,"failed_rows")));
    }
}
