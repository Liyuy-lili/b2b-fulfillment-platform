package cn.iocoder.yudao.module.fulfillment.domain;

import java.util.List;
import java.util.Objects;

/** Uses per-item predicates, so "pieces" and "kilograms" are never summed. */
public final class OrderStatusCalculator {
    private OrderStatusCalculator() {}

    public static OrderStatus calculate(List<OrderQuantities> items, boolean allocationAttempted) {
        Objects.requireNonNull(items);
        if (items.isEmpty()) throw new IllegalArgumentException("An order needs items");
        boolean closed = items.stream().allMatch(q -> q.open().signum() == 0 && q.reserved().signum() == 0);
        boolean anyShipped = items.stream().anyMatch(q -> q.shipped().signum() > 0);
        boolean anyCancelled = items.stream().anyMatch(q -> q.cancelled().signum() > 0);
        if (closed) {
            if (!anyShipped) return OrderStatus.CANCELLED;
            return anyCancelled ? OrderStatus.PARTIALLY_CLOSED : OrderStatus.FULFILLED;
        }
        if (anyShipped) return OrderStatus.PARTIALLY_SHIPPED;
        if (items.stream().allMatch(q -> q.open().signum() == 0)) return OrderStatus.RESERVED;
        return allocationAttempted ? OrderStatus.WAIT_STOCK : OrderStatus.NEW;
    }
}
