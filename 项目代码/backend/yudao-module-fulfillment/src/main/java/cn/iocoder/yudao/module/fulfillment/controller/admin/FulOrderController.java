package cn.iocoder.yudao.module.fulfillment.controller.admin;

import cn.iocoder.yudao.framework.common.pojo.*;
import cn.iocoder.yudao.module.fulfillment.controller.admin.OrderContracts.*;
import cn.iocoder.yudao.module.fulfillment.service.FulOrderService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.NotBlank;
import lombok.RequiredArgsConstructor;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;
import io.swagger.v3.oas.annotations.tags.Tag;
import io.swagger.v3.oas.annotations.Operation;
import static cn.iocoder.yudao.framework.common.pojo.CommonResult.success;

@Tag(name="管理后台 - 履约订单")
@RestController
@RequestMapping("/fulfillment/order")
@RequiredArgsConstructor
@Validated
public class FulOrderController {
    private final FulOrderService service;
    private final cn.iocoder.yudao.module.erp.service.stock.DatabaseCommandRetry retry;

    @PostMapping("/bind")
    @Operation(summary="接管已审核 ERP 销售单")
    @PreAuthorize("@ss.hasPermission('fulfillment:order:bind')")
    public CommonResult<BindResult> bind(@Valid @RequestBody BindRequest request,
            @RequestHeader(value="Idempotency-Key",required=false) @NotBlank @Pattern(regexp="[A-Za-z0-9._:-]{1,128}") String key) {
        return success(retry.run(()->service.bind(request,key)));
    }
    @GetMapping("/get")
    @Operation(summary="履约单与数量快照")
    @PreAuthorize("@ss.hasPermission('fulfillment:order:query')")
    public CommonResult<OrderView> get(@RequestParam @Pattern(regexp="[1-9][0-9]{0,18}") String id) { return success(service.get(id)); }

    @GetMapping("/page")
    @Operation(summary="当前数据范围内的履约单")
    @PreAuthorize("@ss.hasPermission('fulfillment:order:query')")
    public CommonResult<PageResult<OrderView>> page(@Valid PageRequest request) { return success(service.page(request)); }
}
