package cn.iocoder.yudao.module.fulfillment.controller.admin;

import cn.iocoder.yudao.framework.common.pojo.PageParam;
import jakarta.validation.constraints.*;
import lombok.Data;
import lombok.EqualsAndHashCode;
import java.util.List;

public final class OrderContracts {
    public record BindRequest(@NotBlank @Pattern(regexp="[1-9][0-9]{0,18}") String erpOrderId) {}
    public record BindResult(String orderId, String status) {}

    @Data
    @EqualsAndHashCode(callSuper=true)
    public static class PageRequest extends PageParam {
        @Size(max=64) private String orderNo;
        @Pattern(regexp="NEW|WAIT_STOCK|RESERVED|PARTIALLY_SHIPPED|FULFILLED|CANCELLED|PARTIALLY_CLOSED")
        private String status;
    }
    public record ItemView(String id, String erpOrderItemId, String productId, String unitId,
                           String price, String taxPercent, String taxPrice, String totalPrice,
                           String orderedQty, String openQty, String reservedQty, String shippedQty,
                           String cancelledQty, String returnedQty) {}
    public record OrderView(String id, String erpOrderId, String orderNo, String customerId,
                            String ownerUserId, String accountId, String saleUserId,
                            String status, boolean allocationAttempted, String totalPrice,
                            String discountPercent, String discountPrice, String depositPrice,
                            String createTime, List<ItemView> items) {}
}
