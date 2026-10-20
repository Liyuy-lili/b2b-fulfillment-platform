package cn.iocoder.yudao.module.fulfillment.service;
import cn.hutool.crypto.digest.DigestUtil;
import cn.iocoder.yudao.framework.mybatis.core.query.LambdaQueryWrapperX;
import cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder;
import cn.iocoder.yudao.module.fulfillment.dal.dataobject.*;
import cn.iocoder.yudao.module.fulfillment.dal.mysql.*;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;
import java.time.*;
import java.util.List;
import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;
import static cn.iocoder.yudao.module.fulfillment.enums.FulfillmentErrors.*;
@Service @RequiredArgsConstructor @Slf4j
public class FulLogisticsService {
    public record Notice(String provider,String eventId,String shipmentNo,String eventType,@com.fasterxml.jackson.annotation.JsonFormat(shape=com.fasterxml.jackson.annotation.JsonFormat.Shape.STRING) OffsetDateTime occurredAt) {}
    public record Result(String eventId,String outcome) {}
    private final FulCallbackEventMapper callbacks;
    private final FulShipmentMapper shipments;
    private final FulCommandService canonical;
    @Transactional(rollbackFor=Exception.class,isolation=Isolation.READ_COMMITTED,timeout=15)
    public Result receive(Notice notice) {
        long tenant=TenantContextHolder.getRequiredTenantId();
        var hint=shipments.selectOne(new LambdaQueryWrapperX<FulShipmentDO>().eq(FulShipmentDO::getShipmentNo,notice.shipmentNo()));
        if(hint==null) {
            log.warn("Unknown logistics shipment; tenant={}, event={}, shipment={}",tenant,notice.eventId(),notice.shipmentNo());throw exception(CALLBACK_SHIPMENT_UNKNOWN);
        }
        LocalDateTime now=LocalDateTime.now(ZoneOffset.UTC),occurred=notice.occurredAt().withOffsetSameInstant(ZoneOffset.UTC).toLocalDateTime();
        String hash=DigestUtil.sha256Hex(canonical.canonical(List.of("LOGISTICS:v1",notice.provider(),notice.eventId(),notice.shipmentNo(),notice.eventType(),occurred.toString())));
        callbacks.claim(tenant,notice.provider(),notice.eventId(),hint.getId(),hash,notice.eventType(),occurred,now);
        var event=callbacks.lock(tenant,notice.provider(),notice.eventId());
        if(!hash.equals(event.getPayloadHash())) {
            event.setConflictCount(event.getConflictCount()+1).setLastConflictHash(hash);event.setUpdateTime(now);callbacks.updateById(event);
            return new Result(notice.eventId(),"CONFLICT");
        }
        if(!"RECEIVED".equals(event.getResult())) return new Result(notice.eventId(),event.getResult());
        var shipment=shipments.lock(tenant,hint.getId());if(shipment==null) throw exception(CALLBACK_SHIPMENT_UNKNOWN);
        String outcome;
        if("DELIVERED".equals(notice.eventType()) && !"DELIVERED".equals(shipment.getStatus())) {
            shipment.setStatus("DELIVERED").setDeliveredAt(occurred);shipment.setUpdateTime(now);shipment.setUpdater("logistics");shipments.updateById(shipment);outcome="DELIVERED";
        } else outcome="DELIVERED".equals(shipment.getStatus())?"IGNORED_AFTER_DELIVERED":"RECORDED_IN_TRANSIT";
        event.setResult(outcome);event.setUpdateTime(now);event.setUpdater("logistics");callbacks.updateById(event);
        return new Result(notice.eventId(),outcome);
    }
}
