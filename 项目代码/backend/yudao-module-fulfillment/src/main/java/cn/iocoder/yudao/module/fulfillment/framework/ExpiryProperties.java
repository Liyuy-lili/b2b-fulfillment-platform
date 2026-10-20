package cn.iocoder.yudao.module.fulfillment.framework;

import jakarta.validation.constraints.*;
import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Data @Validated @ConfigurationProperties(prefix="fulfillment.expiry")
public class ExpiryProperties {
    @Min(1) @Max(200) private int batchSize=50;
    @Min(1) @Max(20) private int maxBatches=4;
    @Min(250) @Max(3600000) private long delayMs=5000;
    @Min(0) @Max(3600000) private long initialDelayMs=5000;
}
