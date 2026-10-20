package cn.iocoder.yudao.module.fulfillment.controller.admin;
import jakarta.validation.constraints.*;
import java.util.*;
public final class ReconcileContracts {
    private ReconcileContracts() {}
    public record RunRequest(@NotNull Scope scope) {}
    public enum Scope { TENANT }
    public record RunResult(String id,String ruleVersion,String scope,String snapshotAt,String finishedAt,int scannedCount,int differenceCount,Map<String,Integer> tableCounts) {}
    public record FindingView(String id,String runId,String ruleCode,String objectType,String objectId,String orderId,String productId,String warehouseId,String expectedValue,String actualValue,String detail,String resolutionStatus) {}
    public record ReviewRequest(@NotBlank String itemId,@NotBlank @Size(max=256) String note) {}
    public record ReviewView(String id,String itemId,String actorId,String note,String reviewedAt) {}
}
