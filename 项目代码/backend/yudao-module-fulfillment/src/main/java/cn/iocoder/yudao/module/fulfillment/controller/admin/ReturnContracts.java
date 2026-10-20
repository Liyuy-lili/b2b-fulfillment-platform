package cn.iocoder.yudao.module.fulfillment.controller.admin;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.util.List;
import cn.iocoder.yudao.module.fulfillment.controller.admin.ExecutionContracts.QuantityLine;
public final class ReturnContracts {
    public record CreateRequest(@NotBlank @Pattern(regexp="[1-9][0-9]{0,18}") String orderId,
            @NotBlank @Pattern(regexp="[1-9][0-9]{0,18}") String shipmentId,
            @NotNull @Size(min=1,max=100) List<@NotNull @Valid QuantityLine> items,
            @NotBlank @Size(max=128) String reason) {}
    public record ReceiveRequest(@NotBlank @Pattern(regexp="[1-9][0-9]{0,18}") String orderId,
            @NotBlank @Pattern(regexp="[1-9][0-9]{0,18}") String returnId) {}
    public record RejectRequest(@NotBlank @Pattern(regexp="[1-9][0-9]{0,18}") String orderId,
            @NotBlank @Pattern(regexp="[1-9][0-9]{0,18}") String returnId,@NotBlank @Size(max=128) String reason) {}
    public record ReturnResult(String id,String returnNo,String status,String erpSaleReturnId,String orderStatus) {}
    public record ReturnLine(String id,String shipmentItemId,String orderItemId,String quantity,String erpSaleReturnItemId,String erpStockRecordId) {}
    public record AllowanceLine(String shipmentItemId,String orderItemId,String shippedQty,String committedQty,String availableQty) {}
    public record ReturnView(String id,String returnNo,String orderId,String shipmentId,String warehouseId,String status,String reason,
            String erpSaleReturnId,String receivedAt,String rejectedAt,String rejectionReason,String createTime,List<ReturnLine> items) {}
}
