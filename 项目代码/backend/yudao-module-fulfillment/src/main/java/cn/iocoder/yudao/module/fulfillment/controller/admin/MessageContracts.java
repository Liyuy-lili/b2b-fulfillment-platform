package cn.iocoder.yudao.module.fulfillment.controller.admin;
import jakarta.validation.constraints.*;
public final class MessageContracts {
    public enum ReplayAction { REPUBLISH, RETRY_CONSUME }
    public record ReplayRequest(@NotBlank String orderId,@NotBlank @Pattern(regexp="[0-9a-f-]{36}") String eventId,@NotNull ReplayAction action,@NotBlank @Size(max=256) String reason) {}
    public record RebuildRequest(@NotBlank String orderId,@NotBlank @Size(max=256) String reason) {}
    public record InboxView(String id,String status,int attempts,int totalAttempts,int duplicateCount,boolean applied,String nextAttemptAt,String processedAt,String lastError) {}
    public record EventView(String id,String eventId,String orderId,String aggregateVersion,String eventType,int payloadVersion,String status,int attempts,int totalAttempts,String leaseVersion,String leaseUntil,String nextAttemptAt,String lastError,String createdAt,String sentAt,InboxView inbox,String body) {}
    public record DeliveryView(String id,String leaseVersion,String leaseOwner,String result,String error,String startedAt,String finishedAt) {}
    public record ActionView(String id,String eventId,String actorId,String action,String reason,String outcome,String createdAt) {}
    public record ActionResult(String id,String eventId,String action,String outcome) {}
    public record ProjectionView(String orderId,String businessVersion,String observedVersion,String sourceEventId,String snapshotJson,String updatedAt) {}
}
