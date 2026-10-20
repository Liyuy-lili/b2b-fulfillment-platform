package cn.iocoder.yudao.module.fulfillment.framework;

import jakarta.validation.constraints.*;
import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Data @Validated @ConfigurationProperties("fulfillment.jobs")
public class FileJobProperties {
    private boolean enabled=false;
    @NotBlank private String storageRoot="../.local/fulfillment-files/fulfillment";
    @Min(1) @Max(8) private int workers=2;
    @Min(1) @Max(32) private int queueCapacity=4;
    @Min(1) @Max(4) private int tenantConcurrency=2;
    @Min(1) @Max(100) private int tenantPendingLimit=20;
    @Min(1) @Max(1000) private int globalPendingLimit=100;
    @Min(5) @Max(120) private int leaseSeconds=15;
    @Min(1) @Max(10) private int maxAttempts=3;
    @Min(1) @Max(10000) private int importMaxRows=10000;
    @Min(1024) @Max(10485760) private long uploadMaxBytes=10485760;
    @Min(1) @Max(100000) private int exportMaxRows=50000;
    @Min(1024) @Max(52428800) private long outputMaxBytes=52428800;
    @Min(1) @Max(200) private int batchSize=100;
}
