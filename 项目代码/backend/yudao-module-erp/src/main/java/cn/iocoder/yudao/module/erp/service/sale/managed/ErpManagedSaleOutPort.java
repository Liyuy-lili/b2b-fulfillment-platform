package cn.iocoder.yudao.module.erp.service.sale.managed;
import java.math.BigDecimal;
import java.util.List;
/** Internal Java port. No HTTP controller exposes it or any bypass parameter. */
public interface ErpManagedSaleOutPort {
    record Line(long reservationId,long sourceItemId,BigDecimal quantity) {}
    record Request(long sourceOrderId,long warehouseId,List<Line> lines) {}
    record Mapping(long reservationId,long saleOutItemId,long stockRecordId) {}
    record Result(long saleOutId,List<Mapping> mappings) {}
    Result createAndApprove(Request request);
}
