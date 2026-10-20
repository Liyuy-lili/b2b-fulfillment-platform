package cn.iocoder.yudao.module.fulfillment.framework;
import jakarta.validation.constraints.*;
import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;
@Data @Validated @ConfigurationProperties("fulfillment.messages")
public class MessageProperties {
    private boolean enabled=false;
    private boolean publisherEnabled=true;
    private boolean consumerEnabled=true;
    @NotBlank private String host="127.0.0.1";
    @Min(1) @Max(65535) private int port=35672;
    @NotBlank private String username="fulfillment";
    @NotBlank private String password="fulfillment-mq-dev";
    @NotBlank private String virtualHost="fulfillment";
    @Pattern(regexp="[A-Za-z0-9._-]{1,64}") private String namespace="fulfillment.m5";
    @Pattern(regexp="[A-Za-z0-9._-]{1,64}") private String routingKey="events";
    @Min(5) @Max(120) private int leaseSeconds=15;
    @Min(1) @Max(10) private int maxAttempts=5;
    @Min(50) @Max(60000) private long retryBaseMs=1000;
    @Min(1) @Max(20) private int batchSize=5;
    @Min(100) @Max(5000) private int confirmTimeoutMs=3000;
}
