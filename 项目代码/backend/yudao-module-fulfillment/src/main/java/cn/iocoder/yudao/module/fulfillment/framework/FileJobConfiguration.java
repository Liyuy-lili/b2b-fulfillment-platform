package cn.iocoder.yudao.module.fulfillment.framework;

import cn.iocoder.yudao.module.fulfillment.service.*;
import cn.iocoder.yudao.module.erp.service.stock.DatabaseCommandRetry;
import cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder;
import cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.*;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;
import jakarta.annotation.PreDestroy;
import java.util.*;
import java.util.concurrent.*;
import static cn.iocoder.yudao.module.fulfillment.service.JobValues.*;

@Configuration @EnableConfigurationProperties(FileJobProperties.class)
public class FileJobConfiguration {
    @Bean @ConditionalOnProperty(name="fulfillment.jobs.enabled",havingValue="true")
    ThreadPoolTaskScheduler fulfillmentFileJobScheduler(){var s=new ThreadPoolTaskScheduler();s.setPoolSize(1);s.setThreadNamePrefix("ful-job-scan-");s.setWaitForTasksToCompleteOnShutdown(false);return s;}
    @Bean @ConditionalOnProperty(name="fulfillment.jobs.enabled",havingValue="true")
    JobWorker fileJobWorker(FulJobStore store,FulJobProcessor processor,FulJobAuthorization auth,FileJobProperties properties,DatabaseCommandRetry retry,ObjectProvider<FulJobFault> faults){return new JobWorker(store,processor,auth,properties,retry,faults);}
    @Slf4j public static class JobWorker {
        private final FulJobStore store;private final FulJobProcessor processor;private final FulJobAuthorization auth;private final DatabaseCommandRetry retry;private final ObjectProvider<FulJobFault> faults;
        private final ThreadPoolExecutor pool;private final Set<Long> scheduled=ConcurrentHashMap.newKeySet();private final String owner=UUID.randomUUID().toString();
        JobWorker(FulJobStore store,FulJobProcessor processor,FulJobAuthorization auth,FileJobProperties properties,DatabaseCommandRetry retry,ObjectProvider<FulJobFault> faults){
            this.store=store;this.processor=processor;this.auth=auth;this.retry=retry;this.faults=faults;
            pool=new ThreadPoolExecutor(properties.getWorkers(),properties.getWorkers(),0,TimeUnit.SECONDS,new ArrayBlockingQueue<>(properties.getQueueCapacity()),r->{var t=new Thread(r,"ful-file-worker-"+UUID.randomUUID());t.setDaemon(true);return t;},new ThreadPoolExecutor.AbortPolicy());
        }
        @Scheduled(scheduler="fulfillmentFileJobScheduler",fixedDelayString="${fulfillment.jobs.delay-ms:1000}",initialDelayString="${fulfillment.jobs.initial-delay-ms:3000}")
        public void tick(){
            int room=pool.getMaximumPoolSize()-pool.getActiveCount()+pool.getQueue().remainingCapacity();if(room<=0)return;
            for(long id:store.candidates(Math.min(room,32))){
                if(!scheduled.add(id))continue;
                try{pool.execute(()->execute(id));}catch(RejectedExecutionException e){scheduled.remove(id);return;}
            }
        }
        private void execute(long id){
            FulJobStore.Lease lease=null;
            try{
                lease=retry.run(()->store.claim(id,owner));if(lease==null)return;var current=lease;
                faults.orderedStream().forEach(f->f.afterClaim(current.job()));
                if(text(current.job(),"status").equals("CANCEL_REQUESTED")){store.cancelled(current);return;}
                auth.withActor(current.job(),()->{try{processor.run(current);}catch(RuntimeException e){throw e;}catch(Exception e){throw new JobRunFailure(e);}});
            }catch(Cancelled e){if(lease!=null)safeCancel(lease);}
            catch(LostLease e){log.info("Job stale worker ignored job={}",id);}
            catch(Exception error){
                Throwable cause=error instanceof JobRunFailure?error.getCause():error;
                if(lease!=null){try{store.failure(lease,cause instanceof PermanentFailure?cause.getMessage():"JOB_"+cause.getClass().getSimpleName(),cause instanceof PermanentFailure||cause instanceof cn.iocoder.yudao.module.fulfillment.domain.ImportCsv.InvalidCsv||cause instanceof java.nio.charset.CharacterCodingException);}catch(LostLease ignored){log.info("Job failure arrived after lease lost job={}",id);}catch(Exception failure){log.warn("Job failure retained for lease recovery job={} type={}",id,failure.getClass().getSimpleName());}}
                log.warn("Job processing ended job={} type={}",id,cause.getClass().getSimpleName());
            }finally{
                scheduled.remove(id);Long tenant=TenantContextHolder.getTenantId(),actor=SecurityFrameworkUtils.getLoginUserId();faults.orderedStream().forEach(f->f.afterContextCleared(tenant,actor));
            }
        }
        private void safeCancel(FulJobStore.Lease lease){try{store.cancelled(lease);}catch(LostLease ignored){log.info("Cancellation lease recovered elsewhere job={}",lease.id());}}
        public Map<String,Integer> metrics(){return Map.of("active",pool.getActiveCount(),"queued",pool.getQueue().size(),"workers",pool.getMaximumPoolSize(),"queueCapacity",pool.getQueue().size()+pool.getQueue().remainingCapacity());}
        @PreDestroy public void close(){pool.shutdownNow();}
    }
    private static class JobRunFailure extends RuntimeException {JobRunFailure(Throwable cause){super(cause);}}
}
