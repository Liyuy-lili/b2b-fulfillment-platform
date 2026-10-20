package cn.iocoder.yudao.module.fulfillment.framework;
import cn.iocoder.yudao.module.fulfillment.service.FulMessageFault;
import org.springframework.context.annotation.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
@Configuration @Profile("fulfillment-message-test")
public class MessageFaultTestConfiguration {
    @Bean FulMessageFault messageFault(JdbcTemplate jdbc,
            @Value("${fulfillment.test.message-crash:NONE}") String crash,
            @Value("${fulfillment.test.message-append-failure:false}") boolean appendFailure,
            @Value("${fulfillment.test.message-consumer-failure:false}") boolean consumerFailure,
            @Value("${fulfillment.test.message-before-claim-barrier:false}") boolean claimBarrier,
            @Value("${fulfillment.test.message-confirm-barrier:false}") boolean confirmBarrier,
            @Value("${fulfillment.test.message-target:SHIPMENT_CONFIRMED}") String target){
        return new FulMessageFault(){
            private boolean claimPassed=false,confirmPassed=false;
            private void barrier(String point){
                String name=jdbc.queryForObject("SELECT CONCAT(?,DATABASE())",String.class,point.equals("CLAIM")?"m5claim:":"m5confirm:");
                System.err.println("M5_BARRIER_"+point+" "+name);System.err.flush();
                Integer locked=jdbc.queryForObject("SELECT GET_LOCK(?,90)",Integer.class,name);
                if(!Integer.valueOf(1).equals(locked))throw new IllegalStateException("M5 test barrier timeout");
                jdbc.queryForObject("SELECT RELEASE_LOCK(?)",Integer.class,name);
            }
            private boolean matches(String id){return target.equals(jdbc.queryForObject("SELECT event_type FROM ful_outbox_event WHERE event_id=?",String.class,id));}
            private void stop(String point,String id){
                if(point.equals(crash)&&matches(id)){System.err.println("M5_CRASH_"+point+" "+id);System.err.flush();Runtime.getRuntime().halt(point.equals("AFTER_CONFIRM")?71:72);}
            }
            @Override public void afterAppend(String type){if(appendFailure&&target.equals(type))throw new IllegalStateException("M5_FAILURE_AFTER_OUTBOX");}
            @Override public void beforeClaim(){if(claimBarrier&&!claimPassed){barrier("CLAIM");claimPassed=true;}}
            @Override public void afterBrokerConfirm(String id){if(confirmBarrier&&!confirmPassed&&matches(id)){barrier("CONFIRM");confirmPassed=true;}stop("AFTER_CONFIRM",id);}
            @Override public void afterProjection(String id){if(consumerFailure&&matches(id))throw new IllegalStateException("M5_FAILURE_AFTER_PROJECTION");}
            @Override public void beforeAck(String id){stop("BEFORE_ACK",id);}
        };
    }
}
