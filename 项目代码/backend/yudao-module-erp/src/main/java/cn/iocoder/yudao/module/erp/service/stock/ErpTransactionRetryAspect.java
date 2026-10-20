package cn.iocoder.yudao.module.erp.service.stock;

import lombok.RequiredArgsConstructor;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.*;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Aspect
@Component
@Order(-100)
@RequiredArgsConstructor
public class ErpTransactionRetryAspect {
    private final DatabaseCommandRetry retry;
    @Around("execution(* cn.iocoder.yudao.module.erp.service..*(..)) && @annotation(org.springframework.transaction.annotation.Transactional)")
    public Object around(ProceedingJoinPoint invocation) {
        return retry.run(()->{
            try { return invocation.proceed(); }
            catch (RuntimeException|Error e) { throw e; }
            catch (Throwable e) { throw new IllegalStateException(e); }
        });
    }
}
