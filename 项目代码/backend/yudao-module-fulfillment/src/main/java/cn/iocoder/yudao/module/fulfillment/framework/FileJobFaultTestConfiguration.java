package cn.iocoder.yudao.module.fulfillment.framework;

import cn.iocoder.yudao.module.fulfillment.service.FulJobFault;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.*;
import org.springframework.jdbc.core.JdbcTemplate;
import java.util.*;
import static cn.iocoder.yudao.module.fulfillment.service.JobValues.*;

/** Java-only test profile: no production HTTP fault switches. */
@Configuration @Profile("fulfillment-file-test") @Slf4j
public class FileJobFaultTestConfiguration {
    @Bean FulJobFault fileJobFault(JdbcTemplate jdbc,
            @Value("${fulfillment.test.job-crash:NONE}") String crash,
            @Value("${fulfillment.test.job-business-failure:false}") boolean businessFailure,
            @Value("${fulfillment.test.job-claim-barrier:false}") boolean claimBarrier,
            @Value("${fulfillment.test.job-row-barrier:false}") boolean rowBarrier,
            @Value("${fulfillment.test.job-publish-barrier:false}") boolean publishBarrier,
            @Value("${fulfillment.test.job-target:0}") long target){
        return new FulJobFault(){
            private boolean claimPassed=false,publishPassed=false,rowPassed=false;
            private boolean matches(Map<String,Object> job){return target==0||number(job,"id")==target;}
            private void barrier(String point){
                String name=jdbc.queryForObject("SELECT CONCAT(?,DATABASE())",String.class,"m6"+point.toLowerCase(Locale.ROOT)+":");
                System.err.println("M6_BARRIER_"+point+" "+name);System.err.flush();
                var locked=jdbc.queryForObject("SELECT GET_LOCK(?,90)",Integer.class,name);if(!Integer.valueOf(1).equals(locked))throw new IllegalStateException("M6_TEST_BARRIER_TIMEOUT");jdbc.queryForObject("SELECT RELEASE_LOCK(?)",Integer.class,name);
            }
            private void crash(String point,Map<String,Object> job,int code){if(crash.equals(point)&&matches(job)){System.err.println("M6_CRASH_"+point+" job="+text(job,"id"));System.err.flush();Runtime.getRuntime().halt(code);}}
            @Override public void afterClaim(Map<String,Object> job){if(!matches(job))return;if(claimBarrier&&!claimPassed){claimPassed=true;barrier("CLAIM");}crash("AFTER_CLAIM",job,80);}
            @Override public void afterRowBusiness(Map<String,Object> job,int row){if(businessFailure&&matches(job))throw new IllegalStateException("M6_FAILURE_AFTER_ERP_DRAFT");}
            @Override public void afterRowCommit(Map<String,Object> job,int row){if(matches(job)&&rowBarrier&&!rowPassed){rowPassed=true;barrier("ROW");}crash("AFTER_ROW",job,81);}
            @Override public void beforeArtifactPublish(Map<String,Object> job){if(!matches(job))return;if(publishBarrier&&!publishPassed){publishPassed=true;barrier("PUBLISH");}crash("BEFORE_PUBLISH",job,82);}
            @Override public void afterContextCleared(Long tenant,Long actor){System.err.println("M6_CONTEXT_CLEAR thread="+Thread.currentThread().getName()+" tenant="+tenant+" actor="+actor);System.err.flush();if(tenant!=null||actor!=null)throw new IllegalStateException("M6_CONTEXT_LEAK");}
        };
    }
}
