package cn.iocoder.yudao.module.fulfillment.controller.admin;
import cn.iocoder.yudao.framework.common.pojo.*;
import cn.iocoder.yudao.module.erp.service.stock.DatabaseCommandRetry;
import cn.iocoder.yudao.module.fulfillment.service.*;
import cn.iocoder.yudao.module.fulfillment.controller.admin.ExecutionContracts.*;
import cn.iocoder.yudao.module.fulfillment.controller.admin.AllocationContracts.AllocateRequest;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import lombok.RequiredArgsConstructor;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;
import org.springframework.security.access.prepost.PreAuthorize;
import java.util.List;
import static cn.iocoder.yudao.framework.common.pojo.CommonResult.success;
@RestController @RequestMapping("/fulfillment") @Validated @RequiredArgsConstructor
public class FulExecutionController {
    private final FulExecutionService execution;
    private final FulWorkbenchService workbench;
    private final DatabaseCommandRetry retry;
    @PostMapping("/order/preview") @PreAuthorize("@ss.hasPermission('fulfillment:order:allocate')")
    public CommonResult<PreviewResult> preview(@Valid @RequestBody AllocateRequest request) { return success(workbench.preview(request)); }
    @GetMapping("/warehouses") @PreAuthorize("@ss.hasPermission('fulfillment:order:query')")
    public CommonResult<List<WarehouseView>> warehouses() { return success(workbench.warehouses()); }
    @PostMapping("/shipment/confirm") @PreAuthorize("@ss.hasPermission('fulfillment:shipment:confirm')")
    public CommonResult<ShipResult> ship(@Valid @RequestBody ShipRequest request,
            @RequestHeader(value="Idempotency-Key",required=false) @NotBlank @Pattern(regexp="[A-Za-z0-9._:-]{1,128}") String key) { return success(retry.run(()->execution.ship(request,key))); }
    @PostMapping("/order/cancel") @PreAuthorize("@ss.hasPermission('fulfillment:order:cancel')")
    public CommonResult<CancelResult> cancel(@Valid @RequestBody CancelRequest request,
            @RequestHeader(value="Idempotency-Key",required=false) @NotBlank @Pattern(regexp="[A-Za-z0-9._:-]{1,128}") String key) { return success(retry.run(()->execution.cancel(request,key))); }
    @GetMapping("/shipment/page") @PreAuthorize("@ss.hasPermission('fulfillment:shipment:query')")
    public CommonResult<PageResult<ShipmentView>> shipments(@RequestParam String orderId,@RequestParam(defaultValue="1") @Min(1) int pageNo,@RequestParam(defaultValue="20") @Min(1) @Max(100) int pageSize) { return success(workbench.shipmentPage(orderId,pageNo,pageSize)); }
    @GetMapping("/shipment/get") @PreAuthorize("@ss.hasPermission('fulfillment:shipment:query')")
    public CommonResult<ShipmentView> shipment(@RequestParam String id) { return success(workbench.shipment(id)); }
    @GetMapping("/order/cancellations") @PreAuthorize("@ss.hasPermission('fulfillment:order:query')")
    public CommonResult<List<CancellationView>> cancellations(@RequestParam String orderId) { return success(workbench.cancellations(orderId)); }
}
