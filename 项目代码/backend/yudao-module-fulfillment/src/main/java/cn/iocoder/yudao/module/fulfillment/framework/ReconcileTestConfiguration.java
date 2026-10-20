package cn.iocoder.yudao.module.fulfillment.framework;
import cn.iocoder.yudao.module.fulfillment.service.ReconcileSnapshotObserver;
import lombok.extern.slf4j.Slf4j;
import org.springframework.context.annotation.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
/** SQL named-lock barrier/fault only in explicit integration-test profile. */
@Configuration @Profile("fulfillment-reconcile-test") @Slf4j
public class ReconcileTestConfiguration {
    @Bean ReconcileSnapshotObserver reconcileTestObserver(JdbcTemplate jdbc,
            @Value("${fulfillment.test.reconcile-barrier:false}") boolean barrier,
            @Value("${fulfillment.test.reconcile-fail:false}") boolean fail){
        return new ReconcileSnapshotObserver(){
            @Override public void afterTable(String table){
                if(table.equals("erp_stock")){
                    String mode=jdbc.queryForObject("SELECT @@transaction_isolation",String.class);
                    if(!"REPEATABLE-READ".equals(mode))throw new IllegalStateException("Expected RR snapshot, actual "+mode);
                    log.info("M4_RECONCILE_ISOLATION {}",mode);
                }
                if(!barrier||!table.equals("erp_stock"))return;
                String name=jdbc.queryForObject("SELECT CONCAT('m4c:',DATABASE())",String.class);
                log.info("M4_RECONCILE_SNAPSHOT_READY {}",name);
                Integer locked=jdbc.queryForObject("SELECT GET_LOCK(?,15)",Integer.class,name);
                if(!Integer.valueOf(1).equals(locked))throw new IllegalStateException("Reconcile test barrier timeout");
                jdbc.queryForObject("SELECT RELEASE_LOCK(?)",Integer.class,name);
            }
            @Override public void afterPersist(){
                String mode=jdbc.queryForObject("SELECT @@transaction_isolation",String.class);
                if(!"READ-COMMITTED".equals(mode))throw new IllegalStateException("Expected restored outer RC, actual "+mode);
                log.info("M4_RECONCILE_OUTER_ISOLATION {}",mode);
                if(fail)throw new IllegalStateException("M4_RECONCILE_FAILURE_AFTER_REPORT");
            }
        };
    }
}
