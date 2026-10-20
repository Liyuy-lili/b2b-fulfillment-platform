package cn.iocoder.yudao.module.fulfillment.domain;

import org.junit.jupiter.api.Test;
import java.math.BigDecimal;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
import static cn.iocoder.yudao.module.fulfillment.domain.AllocationPlanner.*;

class AllocationPlannerTest {
    private static BigDecimal n(String s) { return new BigDecimal(s); }
    @Test void priorityAndIdsAreStableRegardlessOfInputOrder() {
        var demand=List.of(new Demand(1,10,n("7")));
        var supply=List.of(new Supply(10,3,2,n("5")),new Supply(10,2,1,n("2")),new Supply(10,1,1,n("3")));
        var expected=List.of(new Piece(1,10,1,n("3")),new Piece(1,10,2,n("2")),new Piece(1,10,3,n("2")));
        assertEquals(expected,plan(demand,supply,Strategy.PRIORITY_SPLIT).pieces());
        var reversed=new ArrayList<>(supply);Collections.reverse(reversed);
        assertEquals(expected,plan(demand,reversed,Strategy.PRIORITY_SPLIT).pieces());
    }
    @Test void singleFirstMeansWholeOrderRatherThanOneProduct() {
        var demand=List.of(new Demand(1,10,n("5")),new Demand(2,20,n("6")));
        var supply=List.of(new Supply(10,1,1,n("10")),new Supply(20,1,1,n("3")),new Supply(10,2,2,n("5")),new Supply(20,2,2,n("6")));
        var result=plan(demand,supply,Strategy.SINGLE_FIRST);
        assertTrue(result.sufficient());assertEquals(Set.of(2L),new HashSet<>(result.pieces().stream().map(Piece::warehouseId).toList()));
    }
    @Test void singleFirstFallsBackToPrioritySplit() {
        var result=plan(List.of(new Demand(1,10,n("7"))),List.of(new Supply(10,1,1,n("3")),new Supply(10,2,2,n("4"))),Strategy.SINGLE_FIRST);
        assertTrue(result.sufficient());assertEquals(2,result.pieces().size());
    }
    @Test void repeatedSkuLinesShareTheRemainingBalance() {
        var demand=List.of(new Demand(2,10,n("4")),new Demand(1,10,n("4")));
        assertFalse(plan(demand,List.of(new Supply(10,1,1,n("5"))),Strategy.PRIORITY_SPLIT).sufficient());
        var result=plan(demand,List.of(new Supply(10,1,1,n("5")),new Supply(10,2,2,n("3"))),Strategy.SINGLE_FIRST);
        assertTrue(result.sufficient());assertEquals(List.of(new Piece(1,10,1,n("4")),new Piece(2,10,1,n("1")),new Piece(2,10,2,n("3"))),result.pieces());
    }
    @Test void insufficientSecondSkuReturnsNoPartialPlan() {
        var result=plan(List.of(new Demand(1,10,n("2")),new Demand(2,20,n("3"))),List.of(new Supply(10,1,1,n("2")),new Supply(20,1,1,n("2"))),Strategy.PRIORITY_SPLIT);
        assertFalse(result.sufficient());assertTrue(result.pieces().isEmpty());
    }
    @Test void preservesSixDecimalsBeyondDoubleIntegerPrecision() {
        var quantity=n("9007199254740992.000001");
        assertFalse(plan(List.of(new Demand(1,10,quantity)),List.of(new Supply(10,1,1,n("9007199254740992.000000"))),Strategy.PRIORITY_SPLIT).sufficient());
        assertEquals(quantity,plan(List.of(new Demand(1,10,quantity)),List.of(new Supply(10,1,1,quantity)),Strategy.PRIORITY_SPLIT).pieces().get(0).quantity());
    }
    @Test void rejectsAmbiguousInputRatherThanSilentlyMergingIt() {
        assertThrows(IllegalArgumentException.class,()->plan(List.of(new Demand(1,10,n("1")),new Demand(1,10,n("1"))),List.of(),Strategy.PRIORITY_SPLIT));
        assertThrows(IllegalArgumentException.class,()->plan(List.of(new Demand(1,10,n("1"))),List.of(new Supply(10,1,1,n("1")),new Supply(10,1,1,n("1"))),Strategy.PRIORITY_SPLIT));
    }
}
