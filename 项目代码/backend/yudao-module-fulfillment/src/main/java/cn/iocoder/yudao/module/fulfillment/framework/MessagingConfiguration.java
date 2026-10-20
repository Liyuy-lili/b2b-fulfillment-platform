package cn.iocoder.yudao.module.fulfillment.framework;
import cn.iocoder.yudao.framework.tenant.core.service.TenantFrameworkService;
import cn.iocoder.yudao.module.erp.service.stock.DatabaseCommandRetry;
import cn.iocoder.yudao.module.fulfillment.service.*;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.*;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;
@Configuration @EnableConfigurationProperties(MessageProperties.class)
public class MessagingConfiguration {
    @Configuration @EnableScheduling @ConditionalOnProperty(name="fulfillment.messages.enabled",havingValue="true")
    static class Workers {
        private ThreadPoolTaskScheduler scheduler(String prefix){var s=new ThreadPoolTaskScheduler();s.setPoolSize(1);s.setThreadNamePrefix(prefix);s.setRemoveOnCancelPolicy(true);s.setWaitForTasksToCompleteOnShutdown(true);s.setAwaitTerminationSeconds(10);return s;}
        @Bean("fulfillmentMessagePublisherScheduler") ThreadPoolTaskScheduler publisher(){return scheduler("ful-outbox-");}
        @Bean("fulfillmentMessageConsumerScheduler") ThreadPoolTaskScheduler consumer(){return scheduler("ful-inbox-");}
        @Bean FulMessageWorker messageWorker(FulMessageStore store,FulMessageConsumerService service,FulRabbitTransport transport,MessageProperties properties,TenantFrameworkService tenants,DatabaseCommandRetry retry,ObjectProvider<FulMessageFault> faults){return new FulMessageWorker(store,service,transport,properties,tenants,retry,faults);}
    }
}
