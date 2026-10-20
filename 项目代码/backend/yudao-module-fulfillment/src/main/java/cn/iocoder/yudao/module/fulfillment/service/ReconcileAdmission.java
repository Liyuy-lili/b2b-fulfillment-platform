package cn.iocoder.yudao.module.fulfillment.service;
import org.springframework.stereotype.Component;
import java.util.concurrent.*;
import java.util.function.Supplier;
import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;
import static cn.iocoder.yudao.module.fulfillment.enums.FulfillmentErrors.RECONCILE_BUSY;
/** Before acquiring any transaction connection. Bounds this JVM's expensive scans;
 * database idempotency still handles duplicates across JVMs. This is no stock lock.
 */
@Component
public class ReconcileAdmission {
    private final Semaphore permits=new Semaphore(1,true);
    public <T> T run(Supplier<T> work){
        boolean acquired=false;
        try{
            acquired=permits.tryAcquire(5,TimeUnit.SECONDS);
            if(!acquired)throw exception(RECONCILE_BUSY);
            return work.get();
        }catch(InterruptedException e){Thread.currentThread().interrupt();throw exception(RECONCILE_BUSY);}
        finally{if(acquired)permits.release();}
    }
}
