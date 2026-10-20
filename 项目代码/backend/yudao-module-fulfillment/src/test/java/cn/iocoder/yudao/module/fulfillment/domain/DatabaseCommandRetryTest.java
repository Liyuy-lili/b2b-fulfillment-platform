package cn.iocoder.yudao.module.fulfillment.domain;

import cn.iocoder.yudao.module.erp.service.stock.DatabaseCommandRetry;
import cn.iocoder.yudao.framework.common.exception.ServiceException;
import org.junit.jupiter.api.Test;
import org.springframework.dao.CannotAcquireLockException;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import java.util.concurrent.atomic.AtomicInteger;
import static org.junit.jupiter.api.Assertions.*;

class DatabaseCommandRetryTest {
    private final DatabaseCommandRetry retry=new DatabaseCommandRetry();
    @Test void restartsWholeOperationAfterLockFailures() {
        var attempts=new AtomicInteger();
        assertEquals("ok",retry.run(()->{if(attempts.incrementAndGet()<3)throw new CannotAcquireLockException("test");return "ok";}));
        assertEquals(3,attempts.get());
    }
    @Test void capsAttemptsAndDoesNotRetryBusinessErrors() {
        var attempts=new AtomicInteger();
        var error=assertThrows(ServiceException.class,()->retry.run(()->{attempts.incrementAndGet();throw new CannotAcquireLockException("test");}));
        assertEquals(1030198000,error.getCode());assertEquals(3,attempts.get());
        attempts.set(0);
        assertThrows(IllegalArgumentException.class,()->retry.run(()->{attempts.incrementAndGet();throw new IllegalArgumentException("business validation");}));
        assertEquals(1,attempts.get());
    }
    @Test void joinedTransactionPropagatesFailureToItsOutermostBoundary() {
        var attempts=new AtomicInteger();TransactionSynchronizationManager.setActualTransactionActive(true);
        try {
            assertThrows(CannotAcquireLockException.class,()->retry.run(()->{attempts.incrementAndGet();throw new CannotAcquireLockException("test");}));
            assertEquals(1,attempts.get());
        } finally {TransactionSynchronizationManager.clear();}
    }
}
