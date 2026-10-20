package cn.iocoder.yudao.module.erp.service.sale.managed;
import java.math.BigDecimal;
import java.util.List;
/** Java-only controlled receipt. The caller owns the managed source/order/stock locks and transaction. */
public interface ErpManagedSaleReturnPort {
    record Line(long returnItemId,long saleOutItemId,BigDecimal quantity) {}
    record Request(long sourceOrderId,long saleOutId,long warehouseId,List<Line> lines) {}
    record Mapping(long returnItemId,long saleReturnItemId,long stockRecordId) {}
    record Result(long saleReturnId,List<Mapping> mappings) {}
    Result receiveAndApprove(Request request);
}
