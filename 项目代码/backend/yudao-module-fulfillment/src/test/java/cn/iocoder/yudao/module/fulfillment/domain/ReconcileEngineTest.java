package cn.iocoder.yudao.module.fulfillment.domain;
import org.junit.jupiter.api.Test;
import java.util.*;
import java.math.BigDecimal;
import static org.junit.jupiter.api.Assertions.*;
import static cn.iocoder.yudao.module.fulfillment.domain.ReconcileEngine.*;
class ReconcileEngineTest {
    private Row row(Object... fields){Map<String,Object> m=new HashMap<>();for(int i=0;i<fields.length;i+=2)m.put((String)fields[i],fields[i+1]);return new Row(m);}
    private Map<String,List<Row>> stock(){return new HashMap<>(Map.of("erp_stock",List.of(row("id",1L,"product_id",2L,"warehouse_id",3L,"count",new BigDecimal("1.000001"),"ful_reserved_count",BigDecimal.ZERO)),"erp_stock_record",List.of(row("id",4L,"product_id",2L,"warehouse_id",3L,"count",new BigDecimal("1.000001"),"total_count",new BigDecimal("1.000001")))));}
    @Test void exactMicroQuantityClean(){assertTrue(new ReconcileEngine(stock(),20).check().isEmpty());}
    @Test void missingStockDetectedEvenIfLedgerNetsZero(){var d=stock();d.remove("erp_stock");d.put("erp_stock_record",List.of(row("id",4L,"product_id",2L,"warehouse_id",3L,"count",0)));assertEquals("STOCK_MISSING",new ReconcileEngine(d,20).check().get(0).ruleCode());}
    @Test void physicalDifferenceKeepsExactDecimal(){var d=stock();d.get("erp_stock").get(0).values().put("count",new BigDecimal("1.000002"));var f=new ReconcileEngine(d,20).check();assertEquals(1,f.size());assertEquals("1.000001",f.get(0).expectedValue());assertEquals("1.000002",f.get(0).actualValue());}
    @Test void reservationLedgerDoesNotCountAsPhysical(){var d=stock();d.put("ful_stock_ledger",List.of(row("id",5L,"product_id",2L,"warehouse_id",3L,"reservation_id",99L,"held_delta",new BigDecimal("0.000001"))));var f=new ReconcileEngine(d,20).check();assertFalse(f.stream().anyMatch(x->x.ruleCode().equals("STOCK_H_LEDGER")));assertTrue(f.stream().anyMatch(x->x.ruleCode().equals("STOCK_R_LEDGER")));assertTrue(f.stream().anyMatch(x->x.ruleCode().equals("RESERVATION_LEDGER_ORIGIN")));}
    @Test void differenceLimitFailsInsteadOfReturningTruncatedSuccess(){var d=stock();d.get("erp_stock").get(0).values().put("ful_reserved_count",new BigDecimal("0.1"));assertThrows(LimitExceeded.class,()->new ReconcileEngine(d,1).check());}
    @Test void cancelledErpPhysicalEntriesNetToZero(){var d=stock();d.get("erp_stock").get(0).values().put("count",BigDecimal.ZERO);d.put("erp_stock_record",List.of(row("id",4L,"product_id",2L,"warehouse_id",3L,"count",new BigDecimal("1.000001"),"total_count",new BigDecimal("1.000001")),row("id",5L,"product_id",2L,"warehouse_id",3L,"count",new BigDecimal("-1.000001"),"total_count",BigDecimal.ZERO)));assertTrue(new ReconcileEngine(d,20).check().isEmpty());}
    @Test void engineDoesNotChangeInput(){var d=stock();String before=d.toString();new ReconcileEngine(d,20).check();assertEquals(before,d.toString());}
}
