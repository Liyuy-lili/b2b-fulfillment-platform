package cn.iocoder.yudao.module.fulfillment.controller.admin;
import cn.iocoder.yudao.framework.common.pojo.*;
import cn.iocoder.yudao.module.erp.service.stock.DatabaseCommandRetry;
import cn.iocoder.yudao.module.fulfillment.service.FulReturnService;
import cn.iocoder.yudao.module.fulfillment.controller.admin.ReturnContracts.*;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import lombok.RequiredArgsConstructor;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;
import org.springframework.security.access.prepost.PreAuthorize;
import static cn.iocoder.yudao.framework.common.pojo.CommonResult.success;
@RestController @RequestMapping("/fulfillment/return") @Validated @RequiredArgsConstructor
public class FulReturnController {
    private final FulReturnService service;
    private final DatabaseCommandRetry retry;
    @PostMapping("/create") @PreAuthorize("@ss.hasPermission('fulfillment:return:create')")
    public CommonResult<ReturnResult> create(@Valid @RequestBody CreateRequest request,
            @RequestHeader(value="Idempotency-Key",required=false) @NotBlank @Pattern(regexp="[A-Za-z0-9._:-]{1,128}") String key) {return success(retry.run(()->service.create(request,key)));}
    @PostMapping("/receive") @PreAuthorize("@ss.hasPermission('fulfillment:return:receive')")
    public CommonResult<ReturnResult> receive(@Valid @RequestBody ReceiveRequest request,
            @RequestHeader(value="Idempotency-Key",required=false) @NotBlank @Pattern(regexp="[A-Za-z0-9._:-]{1,128}") String key) {return success(retry.run(()->service.receive(request,key)));}
    @PostMapping("/reject") @PreAuthorize("@ss.hasPermission('fulfillment:return:reject')")
    public CommonResult<ReturnResult> reject(@Valid @RequestBody RejectRequest request,
            @RequestHeader(value="Idempotency-Key",required=false) @NotBlank @Pattern(regexp="[A-Za-z0-9._:-]{1,128}") String key) {return success(retry.run(()->service.reject(request,key)));}
    @GetMapping("/get") @PreAuthorize("@ss.hasPermission('fulfillment:return:query')")
    public CommonResult<ReturnView> get(@RequestParam String id) {return success(service.get(id));}
    @GetMapping("/allowance") @PreAuthorize("@ss.hasPermission('fulfillment:return:query')")
    public CommonResult<java.util.List<AllowanceLine>> allowance(@RequestParam String orderId,@RequestParam String shipmentId) {return success(service.allowance(orderId,shipmentId));}
    @GetMapping("/page") @PreAuthorize("@ss.hasPermission('fulfillment:return:query')")
    public CommonResult<PageResult<ReturnView>> page(@RequestParam String orderId,@RequestParam(defaultValue="1") @Min(1) int pageNo,
            @RequestParam(defaultValue="20") @Min(1) @Max(100) int pageSize) {return success(service.page(orderId,pageNo,pageSize));}
}
