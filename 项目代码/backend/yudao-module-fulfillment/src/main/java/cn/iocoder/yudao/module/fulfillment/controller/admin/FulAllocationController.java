package cn.iocoder.yudao.module.fulfillment.controller.admin;

import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder;
import cn.iocoder.yudao.module.erp.dal.mysql.stock.ErpStockMapper;
import cn.iocoder.yudao.module.erp.dal.mysql.product.ErpProductMapper;
import cn.iocoder.yudao.module.erp.service.stock.DatabaseCommandRetry;
import cn.iocoder.yudao.module.erp.service.stock.ErpWarehouseService;
import cn.iocoder.yudao.module.fulfillment.controller.admin.AllocationContracts.*;
import cn.iocoder.yudao.module.fulfillment.service.FulAllocationService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import lombok.RequiredArgsConstructor;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;
import org.springframework.security.access.prepost.PreAuthorize;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.List;
import static cn.iocoder.yudao.framework.common.pojo.CommonResult.success;
import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;
import static cn.iocoder.yudao.module.fulfillment.enums.FulfillmentErrors.WAREHOUSE_NOT_ACCESSIBLE;

@RestController
@RequestMapping("/fulfillment")
@Validated
@RequiredArgsConstructor
@Tag(name="管理后台 - 履约预占与库存")
public class FulAllocationController {
    private final FulAllocationService service;
    private final cn.iocoder.yudao.module.fulfillment.service.FulWarehouseAccess warehouseAccess;
    private final DatabaseCommandRetry retry;
    private final ErpStockMapper stocks;
    private final ErpWarehouseService warehouses;
    private final ErpProductMapper products;

    @PostMapping("/order/allocate")
    @PreAuthorize("@ss.hasPermission('fulfillment:order:allocate')")
    public CommonResult<AllocationResult> allocate(@Valid @RequestBody AllocateRequest request,
            @RequestHeader(value="Idempotency-Key",required=false) @NotBlank @Pattern(regexp="[A-Za-z0-9._:-]{1,128}") String key) {
        return success(retry.run(()->service.allocate(request,key)));
    }
    @PostMapping("/order/release")
    @PreAuthorize("@ss.hasPermission('fulfillment:order:release')")
    public CommonResult<ReleaseResult> release(@Valid @RequestBody ReleaseRequest request,
            @RequestHeader(value="Idempotency-Key",required=false) @NotBlank @Pattern(regexp="[A-Za-z0-9._:-]{1,128}") String key) {
        return success(retry.run(()->service.release(request,key)));
    }
    @GetMapping("/order/reservations")
    @PreAuthorize("@ss.hasPermission('fulfillment:order:query')")
    public CommonResult<List<ReservationView>> reservations(@RequestParam @Pattern(regexp="[1-9][0-9]{0,18}") String orderId) {
        return success(service.reservationList(orderId));
    }
    @GetMapping("/stock/get")
    @PreAuthorize("@ss.hasPermission('fulfillment:stock:query')")
    public CommonResult<StockView> stock(@RequestParam @Positive Long productId,@RequestParam @Positive Long warehouseId) {
        if(warehouses.getWarehouse(warehouseId)==null || products.selectById(productId)==null) throw exception(WAREHOUSE_NOT_ACCESSIBLE);
        warehouseAccess.require(warehouseId,false);
        var balance=stocks.snapshot(TenantContextHolder.getRequiredTenantId(),productId,warehouseId);
        return success(new StockView(productId.toString(),warehouseId.toString(),balance==null?"0.000000":balance.getCount().toPlainString(),balance==null?"0.000000":balance.getFulReservedCount().toPlainString(),balance==null?"0.000000":balance.available().setScale(6).toPlainString()));
    }
}
