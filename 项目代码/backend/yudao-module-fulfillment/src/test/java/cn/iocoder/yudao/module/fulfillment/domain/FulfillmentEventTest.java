package cn.iocoder.yudao.module.fulfillment.domain;
import org.junit.jupiter.api.Test;
import java.time.Instant;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
class FulfillmentEventTest {
    private FulfillmentEvent event(int payload,String version,String order){
        var item=new FulfillmentEvent.Item("1","2","3","1.000001","1.000001","0.000000","0.000000","0.000000","0.000000");
        return new FulfillmentEvent(UUID.randomUUID().toString(),"1","9223372036854775807",version,FulfillmentEvent.Type.ORDER_BOUND,payload,Instant.now().toString(),UUID.randomUUID().toString(),new FulfillmentEvent.Snapshot(order,"XSDD",version,"NEW",List.of(item)));
    }
    @Test void wireIdsAndMicroQuantitiesRemainStrings(){var e=event(1,"0","9223372036854775807");assertDoesNotThrow(e::validate);assertEquals("1.000001",e.data().items().get(0).orderedQty());}
    @Test void unsupportedPayloadRejected(){assertThrows(IllegalArgumentException.class,()->event(2,"0","9223372036854775807").validate());}
    @Test void mismatchedAggregateRejected(){assertThrows(IllegalArgumentException.class,()->event(1,"0","1").validate());}
    @Test void negativeVersionRejected(){assertThrows(IllegalArgumentException.class,()->event(1,"-1","9223372036854775807").validate());}
    @Test void retryHasBoundedJitterAndCeiling(){for(int n=1;n<=10;n++){long delay=FulfillmentEvent.retryDelayMs("event",n,1000);long base=Math.min(60000,1000L*(1L<<(n-1)));assertTrue(delay>=base&&delay<=Math.min(60000,base+base/5));}}
    @Test void repeatedRetryCalculationStable(){assertEquals(FulfillmentEvent.retryDelayMs("event",3,200),FulfillmentEvent.retryDelayMs("event",3,200));}
    @Test void retryParametersValidated(){assertThrows(IllegalArgumentException.class,()->FulfillmentEvent.retryDelayMs("event",0,100));assertThrows(IllegalArgumentException.class,()->FulfillmentEvent.retryDelayMs("event",1,0));}
}
