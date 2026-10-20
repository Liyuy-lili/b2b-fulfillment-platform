package cn.iocoder.yudao.module.fulfillment.service;

import cn.iocoder.yudao.framework.security.core.LoginUser;
import cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils;
import cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder;
import cn.iocoder.yudao.framework.tenant.core.service.TenantFrameworkService;
import cn.iocoder.yudao.framework.tenant.core.util.TenantUtils;
import cn.iocoder.yudao.module.system.api.permission.PermissionApi;
import cn.iocoder.yudao.module.fulfillment.controller.admin.FileJobContracts.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import java.util.*;
import static cn.iocoder.yudao.module.fulfillment.service.JobValues.*;
import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;
import static cn.iocoder.yudao.framework.common.exception.enums.GlobalErrorCodeConstants.FORBIDDEN;
import static cn.iocoder.yudao.module.fulfillment.enums.FulfillmentErrors.JOB_PERMISSION_REVOKED;

@Service @RequiredArgsConstructor
public class FulJobAuthorization {
    private final PermissionApi permissions;private final FulWarehouseAccess warehouses;
    private final TenantFrameworkService tenants;private final JdbcTemplate jdbc;private final ObjectMapper json;
    public long actor(){return SecurityFrameworkUtils.getLoginUserId();}
    public void permit(long actor,String permission){if(!permissions.hasAnyPermissions(actor,permission))throw exception(FORBIDDEN);}
    public void importPermission(long actor){permit(actor,"fulfillment:job:query");permit(actor,"fulfillment:job:import");permit(actor,"erp:sale-order:create");}
    public Scope freeze(ExportRequest r){
        long actor=actor();permit(actor,"fulfillment:job:export");
        if(r.dataset()==Dataset.ORDER){permit(actor,"fulfillment:order:query");if(r.warehouseIds()!=null&&!r.warehouseIds().isEmpty())throw exception(JOB_PERMISSION_REVOKED);
            boolean all=warehouses.admin(actor);return new Scope(List.of(),all?null:actor,r.orderStatus(),all);}
        if(r.orderStatus()!=null)throw exception(JOB_PERMISSION_REVOKED);
        permit(actor,"fulfillment:warehouse:query");return new Scope(warehouses.freeze(r.warehouseIds(),false),null,null,false);
    }
    public Scope scope(Map<String,Object> job){try{return json.readValue(text(job,"scope_json"),Scope.class);}catch(Exception e){throw new PermanentFailure("INVALID_SAVED_SCOPE");}}
    public void check(Map<String,Object> job){
        long tenant=number(job,"tenant_id"),actor=number(job,"actor_id");
        if(!Objects.equals(TenantContextHolder.getTenantId(),tenant))throw new PermanentFailure("TENANT_CONTEXT_MISMATCH");
        try{
            tenants.validTenant(tenant);
            if(jdbc.queryForObject("SELECT COUNT(*) FROM system_users WHERE tenant_id=? AND id=? AND status=0 AND deleted=0",Long.class,tenant,actor)!=1)throw new PermanentFailure("ACTOR_DISABLED");
            if(text(job,"job_type").equals("IMPORT")){importPermission(actor);return;}
            permit(actor,"fulfillment:job:export");var scope=scope(job);
            if(text(job,"dataset").equals("ORDER")){
                permit(actor,"fulfillment:order:query");
                if(scope.allOrders()&&!warehouses.admin(actor)||!scope.allOrders()&&!Objects.equals(scope.ownerId(),actor)&&!warehouses.admin(actor))throw new PermanentFailure("SCOPE_REVOKED");
            }else{permit(actor,"fulfillment:warehouse:query");warehouses.require(actor,scope.warehouseIds(),false);}
        }catch(PermanentFailure e){throw e;}catch(Exception e){
            // Database outages must remain retryable, not be mislabeled revoked.
            if(e instanceof org.springframework.dao.DataAccessException)throw e;
            throw new PermanentFailure("PERMISSION_OR_TENANT_REVOKED");
        }
    }
    /** Originator identity only, no elevated authorities. Permission is rechecked per boundary. */
    public void withActor(Map<String,Object> job,Runnable work){
        long tenant=number(job,"tenant_id"),actor=number(job,"actor_id");
        TenantUtils.execute(tenant,(Runnable)()->{
            var previous=SecurityContextHolder.getContext();
            try{
                check(job);var user=new LoginUser().setId(actor).setTenantId(tenant).setUserType(2);
                var context=SecurityContextHolder.createEmptyContext();context.setAuthentication(new UsernamePasswordAuthenticationToken(user,null,List.of()));SecurityContextHolder.setContext(context);work.run();
            }finally{SecurityContextHolder.setContext(previous);}
        });
    }
    public void downloadCheck(Map<String,Object> job){try{check(job);}catch(PermanentFailure e){throw exception(JOB_PERMISSION_REVOKED);}}
}
