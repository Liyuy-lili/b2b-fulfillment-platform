package cn.iocoder.yudao.module.fulfillment.domain;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

/** Quantities of one item/unit. Never add unrelated product units together. */
public record OrderQuantities(BigDecimal ordered, BigDecimal open, BigDecimal reserved,
                              BigDecimal shipped, BigDecimal cancelled, BigDecimal returned) {
    public OrderQuantities {
        for (BigDecimal value : new BigDecimal[]{ordered, open, reserved, shipped, cancelled, returned}) {
            Objects.requireNonNull(value, "quantity");
            try { value.setScale(6, RoundingMode.UNNECESSARY); }
            catch (ArithmeticException e) { throw new IllegalArgumentException("Quantity exceeds six decimal places", e); }
            if (value.signum() < 0 || value.precision() - value.scale() > 18) {
                throw new IllegalArgumentException("Quantity outside DECIMAL(24,6)");
            }
        }
        if (ordered.signum() <= 0 || ordered.compareTo(open.add(reserved).add(shipped).add(cancelled)) != 0
                || returned.compareTo(shipped) > 0) {
            throw new IllegalArgumentException("Order quantity invariant violated");
        }
    }
}
