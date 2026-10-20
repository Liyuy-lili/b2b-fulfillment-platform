package cn.iocoder.yudao.module.fulfillment.controller.admin;

import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import cn.iocoder.yudao.module.fulfillment.domain.AllocationPlanner.Strategy;
import java.util.List;

public final class AllocationContracts {
    public record AllocateRequest(@NotBlank @Pattern(regexp="[1-9][0-9]{0,18}") String orderId,
            @NotNull Strategy strategy,
            @NotNull @Size(min=1,max=16) List<@NotBlank @Pattern(regexp="[1-9][0-9]{0,18}") String> warehouseIds,
            @NotNull @Min(60) @Max(86400) Integer holdSeconds) {}
    public record ReleaseLine(@NotBlank @Pattern(regexp="[1-9][0-9]{0,18}") String reservationId,
            @NotBlank @Pattern(regexp="[0-9]{1,18}(\\.[0-9]{1,6})?") String quantity) {}
    public record ReleaseRequest(@NotBlank @Pattern(regexp="[1-9][0-9]{0,18}") String orderId,
            @NotNull @Size(min=1,max=100) List<@Valid @NotNull ReleaseLine> items,
            @NotBlank @Size(max=128) String reason) {}
    public record ReservationView(String id,String orderItemId,String productId,String warehouseId,
            String allocatedQty,String heldQty,String consumedQty,String releasedQty,String expireAt) {}
    public record AllocationResult(String orderId,String status,String outcome,List<ReservationView> reservations) {}
    public record ReleasedLine(String reservationId,String quantity) {}
    public record ReleaseResult(String orderId,String status,List<ReleasedLine> released) {}
    public record StockView(String productId,String warehouseId,String physical,String reserved,String available) {}
}
