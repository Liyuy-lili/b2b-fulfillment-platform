package cn.iocoder.yudao.module.fulfillment.controller.admin;
import cn.iocoder.yudao.framework.common.pojo.*;
import cn.iocoder.yudao.module.erp.service.stock.DatabaseCommandRetry;
import cn.iocoder.yudao.module.fulfillment.service.FulReconcileService;
import cn.iocoder.yudao.module.fulfillment.service.ReconcileAdmission;
import cn.iocoder.yudao.module.fulfillment.controller.admin.ReconcileContracts.*;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import lombok.RequiredArgsConstructor;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;
import org.springframework.security.access.prepost.PreAuthorize;
import static cn.iocoder.yudao.framework.common.pojo.CommonResult.success;
@RestController @RequestMapping("/fulfillment/reconcile") @Validated @RequiredArgsConstructor
public class FulReconcileController {
    private final FulReconcileService service;private final DatabaseCommandRetry retry;
    private final ReconcileAdmission admission;
    @PostMapping("/run") @PreAuthorize("@ss.hasPermission('fulfillment:reconcile:run') and @ss.hasPermission('fulfillment:reconcile:query')")
    public CommonResult<RunResult> run(@Valid @RequestBody RunRequest request,@RequestHeader(value="Idempotency-Key",required=false) @NotBlank @Pattern(regexp="[A-Za-z0-9._:-]{1,128}") String key){return success(admission.run(()->retry.run(()->service.run(request,key))));}
    @GetMapping("/get") @PreAuthorize("@ss.hasPermission('fulfillment:reconcile:query')")
    public CommonResult<RunResult> get(@RequestParam String id){return success(service.get(id));}
    @GetMapping("/page") @PreAuthorize("@ss.hasPermission('fulfillment:reconcile:query')")
    public CommonResult<PageResult<RunResult>> page(@RequestParam(defaultValue="1") @Min(1) int pageNo,@RequestParam(defaultValue="20") @Min(1) @Max(100) int pageSize){return success(service.page(pageNo,pageSize));}
    @GetMapping("/items") @PreAuthorize("@ss.hasPermission('fulfillment:reconcile:query')")
    public CommonResult<PageResult<FindingView>> items(@RequestParam String runId,@RequestParam(defaultValue="1") @Min(1) int pageNo,@RequestParam(defaultValue="20") @Min(1) @Max(100) int pageSize,@RequestParam(required=false) @Pattern(regexp="[A-Z_]{1,64}") String ruleCode,@RequestParam(required=false) @Pattern(regexp="OPEN|ACKNOWLEDGED") String resolutionStatus){return success(service.items(runId,pageNo,pageSize,ruleCode,resolutionStatus));}
    @PostMapping("/review") @PreAuthorize("@ss.hasPermission('fulfillment:reconcile:review') and @ss.hasPermission('fulfillment:reconcile:query')")
    public CommonResult<ReviewView> review(@Valid @RequestBody ReviewRequest request,@RequestHeader(value="Idempotency-Key",required=false) @NotBlank @Pattern(regexp="[A-Za-z0-9._:-]{1,128}") String key){return success(retry.run(()->service.review(request,key)));}
    @GetMapping("/reviews") @PreAuthorize("@ss.hasPermission('fulfillment:reconcile:query')")
    public CommonResult<PageResult<ReviewView>> reviews(@RequestParam String runId,@RequestParam String itemId,@RequestParam(defaultValue="1") @Min(1) int pageNo,@RequestParam(defaultValue="20") @Min(1) @Max(100) int pageSize){return success(service.reviews(runId,itemId,pageNo,pageSize));}
}
