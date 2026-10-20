package cn.iocoder.yudao.module.fulfillment.service;

import cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder;
import cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils;
import cn.iocoder.yudao.module.system.api.permission.PermissionApi;
import cn.iocoder.yudao.module.fulfillment.controller.admin.FileJobContracts.*;
import lombok.RequiredArgsConstructor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;
import java.util.*;
import static cn.iocoder.yudao.module.fulfillment.service.JobValues.*;
import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;
import static cn.iocoder.yudao.framework.common.exception.enums.GlobalErrorCodeConstants.FORBIDDEN;
import static cn.iocoder.yudao.module.fulfillment.enums.FulfillmentErrors.*;

@Service @RequiredArgsConstructor
public class FulWarehouseAccess {
    private final JdbcTemplate jdbc;private final PermissionApi permissions;
    private final FulCommandService commands;private final FulOperationAudit audit;
    public boolean admin(long actor){return permissions.hasAnyRoles(actor,"super_admin","tenant_admin");}
    public long actor(){return SecurityFrameworkUtils.getLoginUserId();}
    public List<Long> allowed(long actor,boolean operate){
        long tenant=TenantContextHolder.getRequiredTenantId();
        if(admin(actor))return jdbc.queryForList("SELECT id FROM erp_warehouse WHERE tenant_id=? AND deleted=0 AND status=0 ORDER BY id",Long.class,tenant);
        return jdbc.queryForList("SELECT DISTINCT w.id FROM erp_warehouse w JOIN ful_warehouse_grant g ON g.tenant_id=w.tenant_id AND g.warehouse_id=w.id WHERE w.tenant_id=? AND g.user_id=? AND g.deleted=0 AND w.deleted=0 AND w.status=0 AND "+(operate?"g.permission_type='OPERATE'":"g.permission_type IN ('READ','OPERATE')")+" ORDER BY w.id",Long.class,tenant,actor);
    }
    public void require(long warehouse,boolean operate){require(actor(),List.of(warehouse),operate);}
    public void require(long actor,Collection<Long> ids,boolean operate){
        if(!new HashSet<>(allowed(actor,operate)).containsAll(ids))throw exception(WAREHOUSE_SCOPE_DENIED);
    }
    public List<Long> freeze(List<String> requested,boolean operate){
        var allowed=allowed(actor(),operate);
        var ids=requested==null||requested.isEmpty()?allowed:requested.stream().map(FulOrderService::parseId).sorted().toList();
        if(ids.isEmpty()||ids.size()>128||new HashSet<>(ids).size()!=ids.size())throw exception(WAREHOUSE_SCOPE_DENIED);
        require(actor(),ids,operate);return List.copyOf(ids);
    }
    public List<WarehouseScopeView> scope(){
        var read=allowed(actor(),false);var operate=new HashSet<>(allowed(actor(),true));if(read.isEmpty())return List.of();
        var args=new ArrayList<Object>();args.add(TenantContextHolder.getRequiredTenantId());args.addAll(read);
        return jdbc.queryForList("SELECT id,name FROM erp_warehouse WHERE tenant_id=? AND id IN ("+marks(read.size())+") ORDER BY id",args.toArray()).stream()
                .map(r->new WarehouseScopeView(text(r,"id"),text(r,"name"),operate.contains(number(r,"id")))).toList();
    }
    public void reservations(long order,Collection<Long> ids){
        if(ids.isEmpty())return;var args=new ArrayList<Object>();args.add(TenantContextHolder.getRequiredTenantId());args.add(order);args.addAll(ids);
        var warehouses=jdbc.queryForList("SELECT DISTINCT warehouse_id FROM ful_reservation WHERE tenant_id=? AND order_id=? AND id IN ("+marks(ids.size())+")",Long.class,args.toArray());
        require(actor(),warehouses,true);
    }
    public void cancellation(long order,Collection<Long> items){
        var args=new ArrayList<Object>();args.add(TenantContextHolder.getRequiredTenantId());args.add(order);args.addAll(items);
        var ids=jdbc.queryForList("SELECT DISTINCT warehouse_id FROM ful_reservation WHERE tenant_id=? AND order_id=? AND order_item_id IN ("+marks(items.size())+")",Long.class,args.toArray());require(actor(),ids,true);
    }
    public void shipment(long order,long shipment,boolean operate){
        var rows=jdbc.queryForList("SELECT warehouse_id FROM ful_shipment WHERE tenant_id=? AND order_id=? AND id=?",Long.class,TenantContextHolder.getRequiredTenantId(),order,shipment);
        if(rows.isEmpty())throw exception(SHIPMENT_NOT_ACCESSIBLE);require(rows.get(0),operate);
    }
    public void returned(long order,long id,boolean operate){
        var rows=jdbc.queryForList("SELECT warehouse_id FROM ful_return WHERE tenant_id=? AND order_id=? AND id=?",Long.class,TenantContextHolder.getRequiredTenantId(),order,id);
        if(rows.isEmpty())throw exception(RETURN_NOT_ACCESSIBLE);require(rows.get(0),operate);
    }
    @Transactional(rollbackFor=Exception.class,isolation=Isolation.READ_COMMITTED,timeout=10)
    public String grant(GrantRequest r,String key){
        long tenant=TenantContextHolder.getRequiredTenantId(),actor=actor(),user=FulOrderService.parseId(r.userId()),warehouse=FulOrderService.parseId(r.warehouseId());
        if(!admin(actor)||!permissions.hasAnyPermissions(actor,"fulfillment:warehouse:grant"))throw exception(FORBIDDEN);
        if(jdbc.queryForObject("SELECT COUNT(*) FROM system_users WHERE tenant_id=? AND id=? AND deleted=0",Long.class,tenant,user)!=1
                ||jdbc.queryForObject("SELECT COUNT(*) FROM erp_warehouse WHERE tenant_id=? AND id=? AND deleted=0",Long.class,tenant,warehouse)!=1)throw exception(WAREHOUSE_SCOPE_DENIED);
        var c=commands.claim("WAREHOUSE_GRANT",key,commands.canonical(List.of(r.userId(),r.warehouseId(),r.permission(),r.enabled(),r.reason().trim())));
        if(c.getResponseJson()!=null)return commands.replay(c,String.class);
        var before=jdbc.queryForList("SELECT permission_type,deleted FROM ful_warehouse_grant WHERE tenant_id=? AND user_id=? AND warehouse_id=? AND permission_type=?",tenant,user,warehouse,r.permission());
        jdbc.update("INSERT INTO ful_warehouse_grant(tenant_id,user_id,warehouse_id,permission_type,creator,updater,create_time,update_time,deleted) VALUES(?,?,?,?,?,?,UTC_TIMESTAMP(6),UTC_TIMESTAMP(6),?) ON DUPLICATE KEY UPDATE deleted=VALUES(deleted),updater=VALUES(updater),update_time=UTC_TIMESTAMP(6)",tenant,user,warehouse,r.permission(),String.valueOf(actor),String.valueOf(actor),!r.enabled());
        audit.add(tenant,actor,"WAREHOUSE_GRANT","GRANT",user+":"+warehouse,key,r.reason().trim(),before,Map.of("permission",r.permission(),"enabled",r.enabled()));
        return commands.complete(c,"UPDATED");
    }
}
