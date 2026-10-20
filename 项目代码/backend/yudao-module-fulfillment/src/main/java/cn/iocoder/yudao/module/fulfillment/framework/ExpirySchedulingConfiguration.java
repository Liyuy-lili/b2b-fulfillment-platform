package cn.iocoder.yudao.module.fulfillment.framework;

import cn.iocoder.yudao.module.erp.service.stock.DatabaseCommandRetry;
import cn.iocoder.yudao.module.fulfillment.dal.mysql.FulReservationMapper;
import cn.iocoder.yudao.module.fulfillment.service.FulExpiryService;
import cn.iocoder.yudao.framework.tenant.core.service.TenantFrameworkService;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.*;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@Configuration @EnableScheduling @EnableConfigurationProperties(ExpiryProperties.class)
@ConditionalOnProperty(name="fulfillment.expiry.enabled",havingValue="true")
public class ExpirySchedulingConfiguration {
    @Bean("fulfillmentExpiryScheduler")
    ThreadPoolTaskScheduler expiryScheduler() {
        var scheduler=new ThreadPoolTaskScheduler();scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("ful-expiry-");scheduler.setRemoveOnCancelPolicy(true);
        scheduler.setWaitForTasksToCompleteOnShutdown(true);scheduler.setAwaitTerminationSeconds(20);
        return scheduler;
    }
    @Bean
    FulExpiryScanner expiryScanner(FulReservationMapper mapper,FulExpiryService service,DatabaseCommandRetry retry,
                                  TenantFrameworkService tenants,ExpiryProperties properties) {
        return new FulExpiryScanner(mapper,service,retry,tenants,properties);
    }
}
