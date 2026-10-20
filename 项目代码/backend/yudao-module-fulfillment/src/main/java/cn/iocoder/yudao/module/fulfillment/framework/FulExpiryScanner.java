package cn.iocoder.yudao.module.fulfillment.framework;

import cn.iocoder.yudao.framework.tenant.core.service.TenantFrameworkService;
import cn.iocoder.yudao.framework.tenant.core.util.TenantUtils;
import cn.iocoder.yudao.module.erp.service.stock.DatabaseCommandRetry;
import cn.iocoder.yudao.module.fulfillment.dal.mysql.FulReservationMapper;
import cn.iocoder.yudao.module.fulfillment.service.FulExpiryService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import java.time.*;

/** One bounded, keyset-paged pass per tick. A failing row cannot monopolize every first page. */
@Slf4j @RequiredArgsConstructor
public class FulExpiryScanner {
    private static final LocalDateTime START=LocalDateTime.of(1000,1,1,0,0);
    private final FulReservationMapper mapper;
    private final FulExpiryService service;
    private final DatabaseCommandRetry retry;
    private final TenantFrameworkService tenants;
    private final ExpiryProperties properties;
    private LocalDateTime afterTime=START;
    private long afterId=0;

    @Scheduled(scheduler="fulfillmentExpiryScheduler",fixedDelayString="${fulfillment.expiry.delay-ms:5000}",
            initialDelayString="${fulfillment.expiry.initial-delay-ms:5000}")
    public void scan() {
        LocalDateTime cutoff=LocalDateTime.now(ZoneOffset.UTC);
        for(int batch=0;batch<properties.getMaxBatches();batch++) {
            var candidates=mapper.scanExpired(cutoff,afterTime,afterId,properties.getBatchSize());
            if(candidates.isEmpty()) { afterTime=START;afterId=0;return; }
            for(var candidate:candidates) {
                // Cursor is only scan progress, never a claim of business success. End-of-scan wraps and retries failures.
                afterTime=candidate.getExpireAt();afterId=candidate.getId();
                try {
                    TenantUtils.execute(candidate.getTenantId(),(Runnable)()->{
                        tenants.validTenant(candidate.getTenantId());
                        var result=retry.run(()->service.expire(candidate));
                        log.info("Expiry command tenant={} reservation={} outcome={} quantity={}",candidate.getTenantId(),candidate.getId(),result.outcome(),result.releasedQty());
                    });
                } catch(FulExpiryService.CandidateNotDueException ignored) {
                    log.debug("Expiry candidate changed reservation={}",candidate.getId());
                } catch(Exception failure) {
                    log.warn("Expiry command failed; retained for later scan tenant={} reservation={}",candidate.getTenantId(),candidate.getId(),failure);
                }
            }
        }
    }
}
