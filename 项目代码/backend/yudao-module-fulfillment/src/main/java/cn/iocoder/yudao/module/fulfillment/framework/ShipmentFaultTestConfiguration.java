package cn.iocoder.yudao.module.fulfillment.framework;
import cn.iocoder.yudao.module.fulfillment.service.FulExecutionService.ShipmentFault;
import org.springframework.context.annotation.*;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.aspectj.lang.annotation.*;
import org.aspectj.lang.ProceedingJoinPoint;
import cn.iocoder.yudao.module.erp.service.stock.bo.ErpStockRecordCreateReqBO;
import java.util.List;
@Configuration @Profile("fulfillment-fault-test")
public class ShipmentFaultTestConfiguration {
    @Bean @ConditionalOnProperty(name="fulfillment.test.fail-during-erp",havingValue="false",matchIfMissing=true)
    ShipmentFault failAfterErpApproval() { return ()->{ throw new IllegalStateException("M3_TEST_FAILURE_AFTER_ERP_APPROVAL"); }; }

    @Bean @ConditionalOnProperty(name="fulfillment.test.fail-during-erp",havingValue="true")
    DuringErpApproval failDuringErpApproval() { return new DuringErpApproval(); }

    @Aspect
    static class DuringErpApproval {
        @Around("execution(* cn.iocoder.yudao.module.erp.service.stock.ErpStockRecordServiceImpl.createStockRecords(..))")
        Object fail(ProceedingJoinPoint invocation) throws Throwable {
            Object result=invocation.proceed();
            @SuppressWarnings("unchecked")
            var changes=(List<ErpStockRecordCreateReqBO>)invocation.getArgs()[0];
            if(changes.stream().anyMatch(c->Integer.valueOf(50).equals(c.getBizType()))) {
                throw new IllegalStateException("M3_TEST_FAILURE_DURING_ERP_APPROVAL");
            }
            return result;
        }
    }
}
