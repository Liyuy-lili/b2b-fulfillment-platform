package cn.iocoder.yudao.module.fulfillment.controller.app;
import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import cn.iocoder.yudao.framework.tenant.core.aop.TenantIgnore;
import cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder;
import cn.iocoder.yudao.framework.tenant.core.service.TenantFrameworkService;
import cn.iocoder.yudao.module.erp.service.stock.DatabaseCommandRetry;
import cn.iocoder.yudao.module.fulfillment.integration.*;
import cn.iocoder.yudao.module.fulfillment.service.FulLogisticsService;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.annotation.security.PermitAll;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;
import java.time.Instant;
import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;
import static cn.iocoder.yudao.framework.common.pojo.CommonResult.success;
import static cn.iocoder.yudao.module.fulfillment.enums.FulfillmentErrors.*;
@RestController @RequestMapping("/fulfillment/logistics/callback") @RequiredArgsConstructor
public class FulLogisticsCallbackController {
    private final LogisticsProperties properties;
    private final ObjectMapper json;
    private final FulLogisticsService service;
    private final DatabaseCommandRetry retry;
    private final TenantFrameworkService tenants;
    @PostMapping("/{integrationId}") @PermitAll @TenantIgnore
    public CommonResult<FulLogisticsService.Result> receive(@PathVariable String integrationId,@RequestBody byte[] body,
            @RequestHeader(value="X-Logistics-Timestamp",required=false) String timestamp,
            @RequestHeader(value="X-Logistics-Event-Id",required=false) String eventId,
            @RequestHeader(value="X-Logistics-Signature",required=false) String signature) {
        var config=properties.getIntegrations().get(integrationId);
        if(config==null || config.getTenantId()==null) throw exception(CALLBACK_AUTH_INVALID);
        LogisticsSignature.verify(config.getSecret(),timestamp,eventId,signature,body,Instant.now());
        FulLogisticsService.Notice notice;
        try { notice=json.readValue(body,FulLogisticsService.Notice.class); }
        catch(java.io.IOException e) { throw exception(INVALID_COMMAND); }
        if(!eventId.equals(notice.eventId()) || !config.getProvider().equals(notice.provider()) || notice.shipmentNo()==null
                || !notice.shipmentNo().matches("SHP-[a-fA-F0-9-]{36}") || notice.occurredAt()==null
                || !("IN_TRANSIT".equals(notice.eventType()) || "DELIVERED".equals(notice.eventType()))
                || notice.occurredAt().getYear()<2000 || notice.occurredAt().getYear()>2099) throw exception(INVALID_COMMAND);
        Long previous=TenantContextHolder.getTenantId();Boolean ignored=TenantContextHolder.isIgnore();
        try {
            TenantContextHolder.setTenantId(config.getTenantId());TenantContextHolder.setIgnore(false);tenants.validTenant(config.getTenantId());
            var result=retry.run(()->service.receive(notice));
            return "CONFLICT".equals(result.outcome())?CommonResult.error(CALLBACK_CONFLICT):success(result);
        } finally { TenantContextHolder.setTenantId(previous);TenantContextHolder.setIgnore(ignored); }
    }
}
