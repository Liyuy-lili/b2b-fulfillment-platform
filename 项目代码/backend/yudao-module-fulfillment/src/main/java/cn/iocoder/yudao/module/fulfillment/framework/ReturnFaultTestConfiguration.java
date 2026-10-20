package cn.iocoder.yudao.module.fulfillment.framework;
import cn.iocoder.yudao.module.fulfillment.service.FulReturnService.ReturnFault;
import cn.iocoder.yudao.module.erp.service.stock.bo.ErpStockRecordCreateReqBO;
import org.springframework.context.annotation.*;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.aspectj.lang.annotation.*;
import org.aspectj.lang.ProceedingJoinPoint;
import java.util.List;
@Configuration @Profile("fulfillment-return-fault-test")
public class ReturnFaultTestConfiguration {
    @Bean @ConditionalOnProperty(name="fulfillment.test.return-fail-during-erp",havingValue="false",matchIfMissing=true)
    ReturnFault failAfterReturn() {return ()->{throw new IllegalStateException("M4_RETURN_FAILURE_AFTER_ERP");};}
    @Bean @ConditionalOnProperty(name="fulfillment.test.return-fail-during-erp",havingValue="true")
    DuringReturn failDuringReturn() {return new DuringReturn();}
    @Aspect static class DuringReturn {
        @Around("execution(* cn.iocoder.yudao.module.erp.service.stock.ErpStockRecordServiceImpl.createStockRecords(..))")
        Object fail(ProceedingJoinPoint invocation) throws Throwable {
            Object result=invocation.proceed();
            @SuppressWarnings("unchecked") var changes=(List<ErpStockRecordCreateReqBO>)invocation.getArgs()[0];
            if(changes.stream().anyMatch(c->Integer.valueOf(60).equals(c.getBizType()))) throw new IllegalStateException("M4_RETURN_FAILURE_DURING_ERP");
            return result;
        }
    }
}
