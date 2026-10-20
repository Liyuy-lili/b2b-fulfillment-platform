package cn.iocoder.yudao.module.fulfillment.integration;
import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;
import java.util.*;
@Data @Component @ConfigurationProperties(prefix="fulfillment.logistics")
public class LogisticsProperties {
    private Map<String,Integration> integrations=new HashMap<>();
    @Data public static class Integration { private Long tenantId; private String provider; private String secret; }
}
