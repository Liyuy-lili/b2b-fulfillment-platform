package cn.iocoder.yudao.module.fulfillment.controller.admin;
import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder;
import cn.iocoder.yudao.module.fulfillment.controller.admin.ExecutionContracts.SimulateRequest;
import cn.iocoder.yudao.module.fulfillment.integration.*;
import cn.iocoder.yudao.module.fulfillment.service.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.*;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.client.RestClient;
import java.time.*;
import java.util.*;
import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;
import static cn.iocoder.yudao.module.fulfillment.enums.FulfillmentErrors.*;
@RestController @RequestMapping("/fulfillment/logistics") @RequiredArgsConstructor
public class FulLogisticsSimulatorController {
    private final FulWorkbenchService workbench;
    private final LogisticsProperties properties;
    private final Environment environment;
    private final ObjectMapper json;
    @PostMapping("/simulate") @PreAuthorize("@ss.hasPermission('fulfillment:shipment:simulate')")
    public CommonResult<?> simulate(@Valid @RequestBody SimulateRequest request) throws java.io.IOException {
        var shipment=workbench.shipment(request.shipmentId());
        var config=properties.getIntegrations().entrySet().stream().filter(e->Objects.equals(e.getValue().getTenantId(),TenantContextHolder.getRequiredTenantId())).findFirst().orElseThrow(()->exception(CALLBACK_AUTH_INVALID));
        String event=UUID.randomUUID().toString(),timestamp=String.valueOf(Instant.now().getEpochSecond());
        byte[] body=json.writeValueAsBytes(new FulLogisticsService.Notice(config.getValue().getProvider(),event,shipment.shipmentNo(),request.eventType(),OffsetDateTime.now(ZoneOffset.UTC)));
        String response=RestClient.create("http://127.0.0.1:"+environment.getProperty("server.port"))
                .post().uri("/app-api/fulfillment/logistics/callback/"+config.getKey()).contentType(org.springframework.http.MediaType.APPLICATION_JSON)
                .header("X-Logistics-Timestamp",timestamp).header("X-Logistics-Event-Id",event)
                .header("X-Logistics-Signature",LogisticsSignature.sign(config.getValue().getSecret(),timestamp,event,body)).body(body).retrieve().body(String.class);
        return json.readValue(response,CommonResult.class);
    }
}
