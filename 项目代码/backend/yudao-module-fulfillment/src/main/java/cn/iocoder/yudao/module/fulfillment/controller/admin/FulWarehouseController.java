package cn.iocoder.yudao.module.fulfillment.controller.admin;

import cn.iocoder.yudao.framework.common.pojo.*;
import cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder;
import cn.iocoder.yudao.module.fulfillment.controller.admin.FileJobContracts.*;
import cn.iocoder.yudao.module.fulfillment.service.*;
import cn.iocoder.yudao.module.erp.service.stock.DatabaseCommandRetry;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import lombok.RequiredArgsConstructor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;
import java.util.*;
import static cn.iocoder.yudao.module.fulfillment.service.JobValues.*;
import static cn.iocoder.yudao.framework.common.pojo.CommonResult.success;
import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;
import static cn.iocoder.yudao.framework.common.exception.enums.GlobalErrorCodeConstants.FORBIDDEN;
import static cn.iocoder.yudao.module.fulfillment.enums.FulfillmentErrors.*;

/** Warehouse projections intentionally never serialize order financial/customer DTOs. */
@RestController @RequestMapping("/fulfillment/warehouse") @Validated @RequiredArgsConstructor
public class FulWarehouseController {
    private final FulWarehouseAccess access;private final JdbcTemplate jdbc;private final DatabaseCommandRetry retry;private final FulFileJobAdmin jobs;
    private long tenant(){return TenantContextHolder.getRequiredTenantId();}
    @GetMapping("/scope") @PreAuthorize("@ss.hasPermission('fulfillment:warehouse:query')")
    public CommonResult<List<WarehouseScopeView>> scope(){return success(access.scope());}
    @GetMapping("/stock-page") @PreAuthorize("@ss.hasPermission('fulfillment:warehouse:query')")
    public CommonResult<PageResult<WarehouseStock>> stock(@RequestParam @Positive long warehouseId,@RequestParam(defaultValue="1") @Min(1) int pageNo,@RequestParam(defaultValue="10") @Min(1) @Max(50) int pageSize){
        access.require(warehouseId,false);long total=jdbc.queryForObject("SELECT COUNT(*) FROM erp_stock WHERE tenant_id=? AND warehouse_id=? AND deleted=0",Long.class,tenant(),warehouseId);
        var rows=jdbc.queryForList("SELECT id,product_id,warehouse_id,`count`,ful_reserved_count,`count`-ful_reserved_count AS available FROM erp_stock WHERE tenant_id=? AND warehouse_id=? AND deleted=0 ORDER BY id DESC LIMIT ? OFFSET ?",tenant(),warehouseId,pageSize,(pageNo-1L)*pageSize);
        return success(new PageResult<>(rows.stream().map(r->new WarehouseStock(text(r,"id"),text(r,"product_id"),text(r,"warehouse_id"),text(r,"count"),text(r,"ful_reserved_count"),text(r,"available"))).toList(),total));
    }
    @GetMapping("/reservation-page") @PreAuthorize("@ss.hasPermission('fulfillment:warehouse:query')")
    public CommonResult<PageResult<WarehouseReservation>> reservations(@RequestParam @Positive long warehouseId,@RequestParam(defaultValue="1") @Min(1) int pageNo,@RequestParam(defaultValue="10") @Min(1) @Max(50) int pageSize){
        access.require(warehouseId,false);String from=" FROM ful_reservation r JOIN ful_order o ON o.tenant_id=r.tenant_id AND o.id=r.order_id WHERE r.tenant_id=? AND r.warehouse_id=? AND r.deleted=0 AND o.deleted=0 AND r.held_qty>0";
        long total=jdbc.queryForObject("SELECT COUNT(*)"+from,Long.class,tenant(),warehouseId);
        var rows=jdbc.queryForList("SELECT r.id,r.order_id,o.order_no,r.warehouse_id,r.product_id,r.held_qty,r.expire_at"+from+" ORDER BY r.id DESC LIMIT ? OFFSET ?",tenant(),warehouseId,pageSize,(pageNo-1L)*pageSize);
        return success(new PageResult<>(rows.stream().map(r->new WarehouseReservation(text(r,"id"),text(r,"order_id"),text(r,"order_no"),text(r,"warehouse_id"),text(r,"product_id"),text(r,"held_qty"),time(r.get("expire_at")))).toList(),total));
    }
    @GetMapping("/shipment-page") @PreAuthorize("@ss.hasPermission('fulfillment:warehouse:query')")
    public CommonResult<PageResult<WarehouseShipment>> shipments(@RequestParam @Positive long warehouseId,@RequestParam(defaultValue="1") @Min(1) int pageNo,@RequestParam(defaultValue="10") @Min(1) @Max(50) int pageSize){
        access.require(warehouseId,false);long total=jdbc.queryForObject("SELECT COUNT(*) FROM ful_shipment WHERE tenant_id=? AND warehouse_id=? AND deleted=0",Long.class,tenant(),warehouseId);
        var rows=jdbc.queryForList("SELECT id,shipment_no,order_id,warehouse_id,status,shipped_at FROM ful_shipment WHERE tenant_id=? AND warehouse_id=? AND deleted=0 ORDER BY id DESC LIMIT ? OFFSET ?",tenant(),warehouseId,pageSize,(pageNo-1L)*pageSize);
        return success(new PageResult<>(rows.stream().map(r->new WarehouseShipment(text(r,"id"),text(r,"shipment_no"),text(r,"order_id"),text(r,"warehouse_id"),text(r,"status"),time(r.get("shipped_at")))).toList(),total));
    }
    @GetMapping("/shipment-get") @PreAuthorize("@ss.hasPermission('fulfillment:warehouse:query')")
    public CommonResult<Map<String,Object>> shipment(@RequestParam @Positive long id){
        var rows=jdbc.queryForList("SELECT id,shipment_no,order_id,warehouse_id,status,shipped_at FROM ful_shipment WHERE tenant_id=? AND id=? AND deleted=0",tenant(),id);
        if(rows.isEmpty())throw exception(SHIPMENT_NOT_ACCESSIBLE);var head=rows.get(0);access.require(number(head,"warehouse_id"),false);
        var items=jdbc.queryForList("SELECT i.id,o.product_id,i.quantity FROM ful_shipment_item i JOIN ful_order_item o ON o.tenant_id=i.tenant_id AND o.id=i.order_item_id WHERE i.tenant_id=? AND i.shipment_id=? AND i.deleted=0 AND o.deleted=0 ORDER BY i.id LIMIT 1001",tenant(),id);
        if(items.size()>1000)throw exception(INVALID_COMMAND);
        // Explicit String values protect identifiers/quantities and prevent accidental extra fields.
        return success(Map.of("id",text(head,"id"),"shipmentNo",text(head,"shipment_no"),"orderId",text(head,"order_id"),"warehouseId",text(head,"warehouse_id"),"status",text(head,"status"),"shippedAt",time(head.get("shipped_at")),"items",items.stream().map(i->Map.of("id",text(i,"id"),"productId",text(i,"product_id"),"quantity",text(i,"quantity"))).toList()));
    }
    @PostMapping("/grant") @PreAuthorize("@ss.hasPermission('fulfillment:warehouse:grant')")
    public CommonResult<String> grant(@Valid @RequestBody GrantRequest request,@RequestHeader(value="Idempotency-Key",required=false) @NotBlank @Pattern(regexp="[A-Za-z0-9._:-]{1,128}") String key){return success(retry.run(()->access.grant(request,key)));}
    @GetMapping("/grants") @PreAuthorize("@ss.hasPermission('fulfillment:warehouse:grant')")
    public CommonResult<PageResult<GrantView>> grants(@RequestParam @Positive long userId,@RequestParam(defaultValue="1") @Min(1) int pageNo,@RequestParam(defaultValue="10") @Min(1) @Max(50) int pageSize){
        if(!access.admin(access.actor()))throw exception(FORBIDDEN);long total=jdbc.queryForObject("SELECT COUNT(*) FROM ful_warehouse_grant WHERE tenant_id=? AND user_id=?",Long.class,tenant(),userId);
        var rows=jdbc.queryForList("SELECT id,user_id,warehouse_id,permission_type,deleted FROM ful_warehouse_grant WHERE tenant_id=? AND user_id=? ORDER BY id DESC LIMIT ? OFFSET ?",tenant(),userId,pageSize,(pageNo-1L)*pageSize);
        return success(new PageResult<>(rows.stream().map(r->new GrantView(text(r,"id"),text(r,"user_id"),text(r,"warehouse_id"),text(r,"permission_type"),!flag(r,"deleted"))).toList(),total));
    }
    @GetMapping("/audit-page") @PreAuthorize("@ss.hasPermission('fulfillment:audit:query')")
    public CommonResult<PageResult<AuditView>> audit(@RequestParam @Pattern(regexp="JOB|GRANT") String objectType,@RequestParam @Pattern(regexp="[0-9:]{1,64}") String objectId,@RequestParam(defaultValue="1") @Min(1) int pageNo,@RequestParam(defaultValue="10") @Min(1) @Max(50) int pageSize){
        if(!access.admin(access.actor()))throw exception(FORBIDDEN);return success(jobs.auditPage(objectType,objectId,pageNo,pageSize));
    }
}
