package cn.iocoder.yudao.module.fulfillment.controller.admin;

import jakarta.validation.constraints.*;
import java.util.List;

public final class FileJobContracts {
    public enum Dataset { STOCK,ORDER,SHIPMENT }
    public record ImportRequest(@NotBlank @Pattern(regexp="[0-9a-f-]{36}") String fileId,
            @NotBlank @Pattern(regexp="[A-Za-z0-9._-]{1,40}") String sourceSystem) {}
    public record ExportRequest(@NotNull Dataset dataset,@Size(max=128) List<@Pattern(regexp="[1-9][0-9]{0,18}") String> warehouseIds,
            @Pattern(regexp="NEW|WAIT_STOCK|RESERVED|PARTIALLY_SHIPPED|FULFILLED|CANCELLED|PARTIALLY_CLOSED") String orderStatus) {}
    public record ControlRequest(@NotBlank String jobId,@NotBlank @Size(max=256) String reason) {}
    public record UploadView(String fileId,String sha256,long byteSize,String templateVersion) {}
    public record JobResult(String jobId,String outcome) {}
    public record Scope(List<Long> warehouseIds,Long ownerId,String orderStatus,boolean allOrders) {}
    public record JobView(String id,String actorId,String type,String dataset,String status,String sourceSystem,
            int totalRows,int successRows,int failedRows,int pendingRows,boolean prepared,int attempts,int totalAttempts,
            String sourceCursor,String leaseVersion,String lastError,boolean hasInput,boolean hasResult,boolean hasErrors,
            String createdAt,String startedAt,String completedAt,String leaseUntil,String scopeJson) {}
    public record RowView(int rowNo,String status,String externalNo,String erpOrderId,String outcome,String errorCode) {}
    public record AuditView(String id,String actorId,String operation,String objectType,String objectId,String reason,
            String beforeJson,String afterJson,String requestId,String createdAt) {}
    public record GrantRequest(@NotBlank String userId,@NotBlank String warehouseId,@NotBlank @Pattern(regexp="READ|OPERATE") String permission,
            boolean enabled,@NotBlank @Size(max=256) String reason) {}
    public record GrantView(String id,String userId,String warehouseId,String permission,boolean enabled) {}
    public record WarehouseScopeView(String id,String name,boolean canOperate) {}
    public record WarehouseStock(String id,String productId,String warehouseId,String physical,String reserved,String available) {}
    public record WarehouseReservation(String id,String orderId,String orderNo,String warehouseId,String productId,String heldQty,String expireAt) {}
    public record WarehouseShipment(String id,String shipmentNo,String orderId,String warehouseId,String status,String shippedAt) {}
}
