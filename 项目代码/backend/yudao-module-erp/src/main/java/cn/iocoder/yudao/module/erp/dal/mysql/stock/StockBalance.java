package cn.iocoder.yudao.module.erp.dal.mysql.stock;

import lombok.Data;
import java.math.BigDecimal;

/** Current-read projection; the original M0 entity/initialization contract stays intact. */
@Data
public class StockBalance {
    private Long id;
    private Long productId;
    private Long warehouseId;
    private BigDecimal count;
    private BigDecimal fulReservedCount;
    public BigDecimal available() { return count.subtract(fulReservedCount); }
}
