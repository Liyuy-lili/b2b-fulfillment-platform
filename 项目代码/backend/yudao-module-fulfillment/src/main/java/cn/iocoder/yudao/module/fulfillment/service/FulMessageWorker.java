package cn.iocoder.yudao.module.fulfillment.service;
import cn.iocoder.yudao.framework.tenant.core.service.TenantFrameworkService;
import cn.iocoder.yudao.framework.tenant.core.util.TenantUtils;
import cn.iocoder.yudao.module.erp.service.stock.DatabaseCommandRetry;
import cn.iocoder.yudao.module.fulfillment.framework.MessageProperties;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.scheduling.annotation.Scheduled;
import java.util.UUID;
import static cn.iocoder.yudao.module.fulfillment.service.FulMessageStore.*;
@Slf4j @RequiredArgsConstructor
public class FulMessageWorker {
    private final FulMessageStore store;private final FulMessageConsumerService consumer;private final FulRabbitTransport transport;
    private final MessageProperties properties;private final TenantFrameworkService tenants;private final DatabaseCommandRetry retry;
    private final ObjectProvider<FulMessageFault> faults;
    private final String owner=UUID.randomUUID().toString();private long consumerPauseUntil;
    @Scheduled(scheduler="fulfillmentMessagePublisherScheduler",fixedDelayString="${fulfillment.messages.delay-ms:1000}",initialDelayString="${fulfillment.messages.initial-delay-ms:3000}")
    public void publishTick(){
        if(!properties.isPublisherEnabled())return;
        for(int i=0;i<properties.getBatchSize();i++){
            Claim claim;
            try{faults.orderedStream().forEach(FulMessageFault::beforeClaim);claim=retry.run(()->store.claim(owner));}catch(Exception e){log.warn("Outbox claim failed type={}",e.getClass().getSimpleName());return;}
            if(claim==null)return;
            String error;
            try{
                TenantUtils.execute(claim.tenant(),(Runnable)()->tenants.validTenant(claim.tenant()));
                error=transport.publish(claim);
                if(error==null)faults.orderedStream().forEach(f->f.afterBrokerConfirm(claim.eventId()));
            }catch(Exception e){error="PUBLISH_"+e.getClass().getSimpleName();}
            final String result=error;
            try{boolean accepted=retry.run(()->store.finish(claim,result==null,result));log.info("Outbox completion event={} lease={} accepted={} error={}",claim.eventId(),claim.leaseVersion(),accepted,result);}
            catch(Exception e){log.warn("Outbox completion retained for lease recovery event={} type={}",claim.eventId(),e.getClass().getSimpleName());}
        }
    }
    @Scheduled(scheduler="fulfillmentMessageConsumerScheduler",fixedDelayString="${fulfillment.messages.delay-ms:1000}",initialDelayString="${fulfillment.messages.initial-delay-ms:3000}")
    public void consumeTick(){
        if(!properties.isConsumerEnabled())return;
        try{
            for(var row:store.retryCandidates()){
                var e=store.byEvent(text(row,"event_id"));long version=number(row,"version");
                process(e,version);
            }
        }catch(Exception e){log.warn("Inbox retry scan retained type={}",e.getClass().getSimpleName());}
        if(System.nanoTime()<consumerPauseUntil)return;
        for(int i=0;i<properties.getBatchSize();i++){
            try{
                var delivery=transport.receive();if(delivery==null)return;
                Trusted event;
                try{event=store.trusted(delivery.body());}
                catch(PoisonMessage e){transport.reject(delivery.tag());log.warn("Message rejected to DLQ sha256={}",cn.hutool.crypto.digest.DigestUtil.sha256Hex(delivery.body()));continue;}
                process(event,null);
                faults.orderedStream().forEach(f->f.beforeAck(event.event().eventId()));
                // Either local effect committed or durable Inbox retry committed.
                transport.ack(delivery.tag());
            }catch(Exception e){transport.closeConsumer();consumerPauseUntil=System.nanoTime()+5_000_000_000L;log.warn("Consumer channel closed; unacked delivery requeued type={}",e.getClass().getSimpleName());return;}
        }
    }
    private void process(Trusted e,Long expectedVersion){
        TenantUtils.execute(e.tenant(),(Runnable)()->{
            try{tenants.validTenant(e.tenant());retry.run(()->consumer.deliver(e,expectedVersion));}
            catch(Exception failure){retry.run(()->{consumer.failed(e,expectedVersion,"CONSUME_"+failure.getClass().getSimpleName());return true;});}
        });
    }
}
