package cn.iocoder.yudao.module.erp.service.stock;

import cn.iocoder.yudao.framework.common.exception.ErrorCode;
import lombok.extern.slf4j.Slf4j;
import org.springframework.dao.PessimisticLockingFailureException;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import java.util.concurrent.ThreadLocalRandom;
import java.util.function.Supplier;
import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;

/** Runs OUTSIDE the transactional proxy. Never retries inside a failed/joined transaction. */
@Component
@Slf4j
public class DatabaseCommandRetry {
    public static final ErrorCode BUSY=new ErrorCode(1_030_198_000,"DATABASE_COMMAND_BUSY: 并发操作繁忙，请使用原幂等键重试");
    public <T> T run(Supplier<T> command) {
        if (TransactionSynchronizationManager.isActualTransactionActive()) return command.get();
        for (int attempt=1;attempt<=3;attempt++) {
            try { return command.get(); }
            catch (PessimisticLockingFailureException e) {
                if (attempt==3) throw exception(BUSY);
                log.warn("Retry entire database command after lock failure, next attempt={}",attempt+1);
                try { Thread.sleep(ThreadLocalRandom.current().nextLong(20,61)); }
                catch (InterruptedException interrupted) { Thread.currentThread().interrupt();throw exception(BUSY); }
            }
        }
        throw new IllegalStateException("Unreachable retry loop");
    }
}
