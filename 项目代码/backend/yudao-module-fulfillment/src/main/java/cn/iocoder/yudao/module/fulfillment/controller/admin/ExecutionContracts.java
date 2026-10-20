package cn.iocoder.yudao.module.fulfillment.controller.admin;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.util.List;
public final class ExecutionContracts {
    public record QuantityLine(@NotBlank @Pattern(regexp="[1-9][0-9]{0,18}") String id,
            @NotBlank @Pattern(regexp="[0-9]{1,18}(\\.[0-9]{1,6})?") String quantity) {}
    public record ShipRequest(@NotBlank @Pattern(regexp="[1-9][0-9]{0,18}") String orderId,
            @NotBlank @Pattern(regexp="[1-9][0-9]{0,18}") String warehouseId,
            @NotNull @Size(min=1,max=100) List<@NotNull @Valid QuantityLine> items,
            @NotBlank @Size(max=64) String carrierCode,@NotBlank @Size(max=128) String trackingNo) {}
    public record CancelRequest(@NotBlank @Pattern(regexp="[1-9][0-9]{0,18}") String orderId,
            @NotNull @Size(min=1,max=100) List<@NotNull @Valid QuantityLine> items,
            @NotBlank @Size(max=128) String reason) {}
    public record ShipResult(String shipmentId,String shipmentNo,String erpSaleOutId,String orderStatus) {}
    public record CancelResult(String orderId,String orderStatus,List<QuantityLine> cancelled) {}
    public record PreviewLine(String orderItemId,String productId,String warehouseId,String quantity) {}
    public record PreviewStock(String productId,String warehouseId,String physical,String reserved,String available) {}
    public record PreviewResult(String strategy,int strategyVersion,boolean sufficient,List<PreviewLine> plan,List<PreviewStock> stocks,String notice) {}
    public record WarehouseView(String id,String name,Long priority) {}
    public record ShipmentLine(String id,String orderItemId,String reservationId,String quantity,String erpSaleOutItemId) {}
    public record CallbackView(String eventId,String eventType,String outcome,String occurredAt,String receivedAt,int conflictCount) {}
    public record ShipmentView(String id,String shipmentNo,String orderId,String warehouseId,String erpSaleOutId,String status,
            String carrierCode,String trackingNo,String shippedAt,String deliveredAt,List<ShipmentLine> items,List<CallbackView> events) {}
    public record CancellationView(String id,String orderItemId,String quantity,String reason,String createTime) {}
    public record SimulateRequest(@NotBlank String shipmentId,@NotBlank @Pattern(regexp="IN_TRANSIT|DELIVERED") String eventType) {}
}
