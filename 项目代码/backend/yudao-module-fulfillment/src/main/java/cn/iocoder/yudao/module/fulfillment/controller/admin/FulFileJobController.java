package cn.iocoder.yudao.module.fulfillment.controller.admin;

import cn.iocoder.yudao.framework.common.pojo.*;
import cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder;
import cn.iocoder.yudao.module.fulfillment.controller.admin.FileJobContracts.*;
import cn.iocoder.yudao.module.fulfillment.service.*;
import cn.iocoder.yudao.module.fulfillment.framework.FileJobConfiguration.JobWorker;
import cn.iocoder.yudao.module.erp.service.stock.DatabaseCommandRetry;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import java.nio.file.Files;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import static cn.iocoder.yudao.framework.common.pojo.CommonResult.success;

@RestController @RequestMapping("/fulfillment/job") @Validated @RequiredArgsConstructor
public class FulFileJobController {
    private final FulFileJobAdmin service;private final FulJobAuthorization auth;private final FulPrivateFiles files;private final DatabaseCommandRetry retry;private final FulWarehouseAccess warehouses;private final ObjectProvider<JobWorker> workers;
    @PostMapping("/upload") @PreAuthorize("@ss.hasPermission('fulfillment:job:import')")
    public CommonResult<UploadView> upload(@RequestPart MultipartFile file)throws Exception {
        auth.importPermission(auth.actor());var f=files.upload(file,TenantContextHolder.getRequiredTenantId(),auth.actor());return success(new UploadView(f.id(),f.hash(),f.bytes(),"1"));
    }
    @GetMapping("/template") @PreAuthorize("@ss.hasPermission('fulfillment:job:import')")
    public void template(HttpServletResponse response)throws Exception {
        auth.importPermission(auth.actor());response.setContentType("text/csv;charset=UTF-8");response.setHeader("Content-Disposition","attachment; filename=fulfillment-import-v1.csv");response.getOutputStream().write((String.join(",",cn.iocoder.yudao.module.fulfillment.domain.ImportCsv.HEADER)+"\r\n").getBytes(StandardCharsets.UTF_8));
    }
    @PostMapping("/import") @PreAuthorize("@ss.hasPermission('fulfillment:job:import')")
    public CommonResult<JobResult> importJob(@Valid @RequestBody ImportRequest r,@RequestHeader(value="Idempotency-Key",required=false) @NotBlank @Pattern(regexp="[A-Za-z0-9._:-]{1,128}") String key){return success(retry.run(()->service.submitImport(r,key)));}
    @PostMapping("/export") @PreAuthorize("@ss.hasPermission('fulfillment:job:export')")
    public CommonResult<JobResult> exportJob(@Valid @RequestBody ExportRequest r,@RequestHeader(value="Idempotency-Key",required=false) @NotBlank @Pattern(regexp="[A-Za-z0-9._:-]{1,128}") String key){return success(retry.run(()->service.submitExport(r,key)));}
    @PostMapping("/retry") @PreAuthorize("@ss.hasPermission('fulfillment:job:retry')")
    public CommonResult<JobResult> retry(@Valid @RequestBody ControlRequest r,@RequestHeader(value="Idempotency-Key",required=false) @NotBlank @Pattern(regexp="[A-Za-z0-9._:-]{1,128}") String key){return success(retry.run(()->service.control(r,key,true)));}
    @PostMapping("/cancel") @PreAuthorize("@ss.hasPermission('fulfillment:job:cancel')")
    public CommonResult<JobResult> cancel(@Valid @RequestBody ControlRequest r,@RequestHeader(value="Idempotency-Key",required=false) @NotBlank @Pattern(regexp="[A-Za-z0-9._:-]{1,128}") String key){return success(retry.run(()->service.control(r,key,false)));}
    @GetMapping("/get") @PreAuthorize("@ss.hasPermission('fulfillment:job:query')")
    public CommonResult<JobView> get(@RequestParam @Pattern(regexp="[1-9][0-9]{0,18}") String id){return success(service.get(id));}
    @GetMapping("/page") @PreAuthorize("@ss.hasPermission('fulfillment:job:query')")
    public CommonResult<PageResult<JobView>> page(@RequestParam(required=false) @Pattern(regexp="PENDING|RUNNING|RETRY_WAIT|SUCCEEDED|PARTIAL_FAILED|FAILED|CANCEL_REQUESTED|CANCELLED") String status,@RequestParam(defaultValue="1") @Min(1) int pageNo,@RequestParam(defaultValue="10") @Min(1) @Max(50) int pageSize){return success(service.page(status,pageNo,pageSize));}
    @GetMapping("/rows") @PreAuthorize("@ss.hasPermission('fulfillment:job:query')")
    public CommonResult<PageResult<RowView>> rows(@RequestParam @Pattern(regexp="[1-9][0-9]{0,18}") String id,@RequestParam(defaultValue="1") @Min(1) int pageNo,@RequestParam(defaultValue="10") @Min(1) @Max(50) int pageSize){return success(service.rows(id,pageNo,pageSize));}
    @GetMapping("/audits") @PreAuthorize("@ss.hasPermission('fulfillment:job:query')")
    public CommonResult<PageResult<AuditView>> audits(@RequestParam @Pattern(regexp="[1-9][0-9]{0,18}") String id,@RequestParam(defaultValue="1") @Min(1) int pageNo,@RequestParam(defaultValue="10") @Min(1) @Max(50) int pageSize){return success(service.audits(id,pageNo,pageSize));}
    @GetMapping("/download") @PreAuthorize("@ss.hasPermission('fulfillment:job:query')")
    public void download(@RequestParam @Pattern(regexp="[1-9][0-9]{0,18}") String id,@RequestParam @Pattern(regexp="INPUT|RESULT|ERROR") String kind,HttpServletResponse response)throws Exception {
        var file=service.download(id,kind);response.setHeader("Cache-Control","no-store");response.setHeader("X-Content-Type-Options","nosniff");response.setContentType(file.contentType());response.setHeader("Content-Disposition","attachment; filename="+file.name());response.setContentLengthLong(file.bytes());try(var input=Files.newInputStream(file.path())){input.transferTo(response.getOutputStream());}
    }
    @GetMapping("/runtime") @PreAuthorize("@ss.hasPermission('fulfillment:job:query')")
    public CommonResult<Map<String,Object>> runtime(){
        if(!warehouses.admin(auth.actor()))throw cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception(cn.iocoder.yudao.framework.common.exception.enums.GlobalErrorCodeConstants.FORBIDDEN);
        var worker=workers.getIfAvailable();return success(worker==null?Map.of("enabled",false):Map.of("enabled",true,"instance",worker.metrics()));
    }
}
