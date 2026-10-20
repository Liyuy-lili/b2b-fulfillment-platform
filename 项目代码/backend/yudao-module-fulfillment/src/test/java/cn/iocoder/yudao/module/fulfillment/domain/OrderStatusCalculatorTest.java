package cn.iocoder.yudao.module.fulfillment.domain;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import java.math.BigDecimal;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;

class OrderStatusCalculatorTest {
    private static OrderQuantities q(String open,String held,String shipped,String cancelled,String returned) {
        return new OrderQuantities(new BigDecimal("10"),new BigDecimal(open),new BigDecimal(held),
                new BigDecimal(shipped),new BigDecimal(cancelled),new BigDecimal(returned));
    }
    @ParameterizedTest
    @CsvSource({
            "10,0,0,0,0,false,NEW", "10,0,0,0,0,true,WAIT_STOCK",
            "4,6,0,0,0,true,WAIT_STOCK", "0,10,0,0,0,true,RESERVED",
            "5,0,5,0,0,true,PARTIALLY_SHIPPED", "0,5,5,0,0,true,PARTIALLY_SHIPPED",
            "0,0,10,0,0,true,FULFILLED", "0,0,10,0,10,true,FULFILLED",
            "0,0,0,10,0,false,CANCELLED", "0,0,4,6,1,true,PARTIALLY_CLOSED"
    })
    void derivesState(String open,String held,String shipped,String cancelled,String returned,boolean attempted,OrderStatus expected) {
        assertEquals(expected,OrderStatusCalculator.calculate(List.of(q(open,held,shipped,cancelled,returned)),attempted));
    }
    @ParameterizedTest
    @CsvSource({"-1,0,11,0,0", "10,1,0,0,0", "0,0,10,0,11", "10.0000001,0,0,0,0"})
    void rejectsBrokenInvariants(String open,String held,String shipped,String cancelled,String returned) {
        assertThrows(IllegalArgumentException.class,()->q(open,held,shipped,cancelled,returned));
    }
    @Test void handlesDifferentItemUnitsWithoutSummingThem() {
        var small=new OrderQuantities(new BigDecimal("0.000001"),BigDecimal.ZERO,new BigDecimal("0.000001"),BigDecimal.ZERO,BigDecimal.ZERO,BigDecimal.ZERO);
        assertEquals(OrderStatus.WAIT_STOCK,OrderStatusCalculator.calculate(List.of(small,q("10","0","0","0","0")),true));
        assertEquals(OrderStatus.PARTIALLY_CLOSED,OrderStatusCalculator.calculate(List.of(q("0","0","10","0","0"),q("0","0","0","10","0")),true));
    }
    @Test void rejectsEmptyItemsAndOutOfRangeNumbers() {
        assertThrows(IllegalArgumentException.class,()->OrderStatusCalculator.calculate(List.of(),false));
        var tooBig=new BigDecimal("1000000000000000000");
        assertThrows(IllegalArgumentException.class,()->new OrderQuantities(tooBig,tooBig,BigDecimal.ZERO,BigDecimal.ZERO,BigDecimal.ZERO,BigDecimal.ZERO));
        assertThrows(IllegalArgumentException.class,()->new OrderQuantities(BigDecimal.ZERO,BigDecimal.ZERO,BigDecimal.ZERO,BigDecimal.ZERO,BigDecimal.ZERO,BigDecimal.ZERO));
    }
}
