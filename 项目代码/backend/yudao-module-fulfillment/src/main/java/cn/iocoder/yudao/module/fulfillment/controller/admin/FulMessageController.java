package cn.iocoder.yudao.module.fulfillment.controller.admin;
import cn.iocoder.yudao.framework.common.pojo.*;
import cn.iocoder.yudao.module.erp.service.stock.DatabaseCommandRetry;
import cn.iocoder.yudao.module.fulfillment.service.FulMessageAdminService;
import cn.iocoder.yudao.module.fulfillment.controller.admin.MessageContracts.*;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import lombok.RequiredArgsConstructor;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;
import org.springframework.security.access.prepost.PreAuthorize;
import static cn.iocoder.yudao.framework.common.pojo.CommonResult.success;
@RestController @RequestMapping("/fulfillment/message") @Validated @RequiredArgsConstructor
public class FulMessageController {
    private final FulMessageAdminService service;private final DatabaseCommandRetry retry;
    @GetMapping("/page") @PreAuthorize("@ss.hasPermission('fulfillment:message:query')")
    public CommonResult<PageResult<EventView>> page(@RequestParam String orderId,@RequestParam(required=false) @Pattern(regexp="NEW|IN_FLIGHT|RETRY_WAIT|SENT|DEAD") String status,@RequestParam(defaultValue="1") @Min(1) int pageNo,@RequestParam(defaultValue="20") @Min(1) @Max(50) int pageSize){return success(service.page(orderId,status,pageNo,pageSize));}
    @GetMapping("/get") @PreAuthorize("@ss.hasPermission('fulfillment:message:query')")
    public CommonResult<EventView> get(@RequestParam String orderId,@RequestParam String eventId){return success(service.get(orderId,eventId));}
    @GetMapping("/deliveries") @PreAuthorize("@ss.hasPermission('fulfillment:message:query')")
    public CommonResult<PageResult<DeliveryView>> deliveries(@RequestParam String orderId,@RequestParam String eventId,@RequestParam(defaultValue="1") @Min(1) int pageNo,@RequestParam(defaultValue="20") @Min(1) @Max(50) int pageSize){return success(service.deliveries(orderId,eventId,pageNo,pageSize));}
    @GetMapping("/actions") @PreAuthorize("@ss.hasPermission('fulfillment:message:query')")
    public CommonResult<PageResult<ActionView>> actions(@RequestParam String orderId,@RequestParam(defaultValue="1") @Min(1) int pageNo,@RequestParam(defaultValue="20") @Min(1) @Max(50) int pageSize){return success(service.actions(orderId,pageNo,pageSize));}
    @GetMapping("/projection") @PreAuthorize("@ss.hasPermission('fulfillment:message:query')")
    public CommonResult<ProjectionView> projection(@RequestParam String orderId){return success(service.projection(orderId));}
    @PostMapping("/replay") @PreAuthorize("@ss.hasPermission('fulfillment:message:query') and @ss.hasPermission('fulfillment:message:replay')")
    public CommonResult<ActionResult> replay(@Valid @RequestBody ReplayRequest request,@RequestHeader(value="Idempotency-Key",required=false) @NotBlank @Pattern(regexp="[A-Za-z0-9._:-]{1,128}") String key){return success(retry.run(()->service.replay(request,key)));}
    @PostMapping("/rebuild") @PreAuthorize("@ss.hasPermission('fulfillment:message:query') and @ss.hasPermission('fulfillment:message:rebuild')")
    public CommonResult<ActionResult> rebuild(@Valid @RequestBody RebuildRequest request,@RequestHeader(value="Idempotency-Key",required=false) @NotBlank @Pattern(regexp="[A-Za-z0-9._:-]{1,128}") String key){return success(retry.run(()->service.rebuild(request,key)));}
}
