package cn.iocoder.yudao.module.fulfillment.framework;

import cn.iocoder.yudao.module.fulfillment.service.FulExpiryService.ExpiryFault;
import org.springframework.context.annotation.*;

/** Dedicated test process only. No HTTP knob or production bean. */
@Configuration @Profile("fulfillment-expiry-fault-test")
public class ExpiryFaultTestConfiguration {
    @Bean
    ExpiryFault failAfterExpiryWrites() {
        return id->{ throw new IllegalStateException("M4_TEST_FAILURE_AFTER_EXPIRY_WRITES reservation="+id); };
    }
}
