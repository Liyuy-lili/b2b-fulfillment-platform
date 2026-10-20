package cn.iocoder.yudao.module.fulfillment.framework;

import cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder;
import cn.iocoder.yudao.framework.tenant.core.service.TenantFrameworkService;
import cn.iocoder.yudao.module.erp.service.stock.DatabaseCommandRetry;
import cn.iocoder.yudao.module.fulfillment.dal.dataobject.FulReservationDO;
import cn.iocoder.yudao.module.fulfillment.dal.mysql.FulReservationMapper;
import cn.iocoder.yudao.module.fulfillment.service.FulExpiryService;
import org.junit.jupiter.api.*;
import org.mockito.ArgumentCaptor;
import java.time.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;

class FulExpiryScannerTest {
    private final FulReservationMapper mapper=mock(FulReservationMapper.class);
    private final FulExpiryService service=mock(FulExpiryService.class);
    private final TenantFrameworkService tenants=mock(TenantFrameworkService.class);
    private final ExpiryProperties config=new ExpiryProperties();
    private final FulExpiryScanner scanner=new FulExpiryScanner(mapper,service,new DatabaseCommandRetry(),tenants,config);
    private final LocalDateTime deadline=LocalDateTime.of(2026,10,18,0,0);
    private FulReservationDO candidate(long id,long tenant) {
        var r=new FulReservationDO().setId(id).setExpireAt(deadline);r.setTenantId(tenant);return r;
    }
    @AfterEach void clear() { TenantContextHolder.clear(); }
    @Test void tenantContextIsScopedOnSuccessAndFailure() {
        var first=candidate(1,10);var second=candidate(2,20);
        TenantContextHolder.setTenantId(99L);TenantContextHolder.setIgnore(true);
        when(mapper.scanExpired(any(),any(),anyLong(),anyInt())).thenReturn(List.of(first,second),List.of());
        when(service.expire(any())).thenAnswer(call->{
            FulReservationDO r=call.getArgument(0);
            assertEquals(r.getTenantId(),TenantContextHolder.getRequiredTenantId());assertFalse(TenantContextHolder.isIgnore());
            if(r==first) throw new IllegalStateException("test failure");
            return new FulExpiryService.ExpiryResult("2","EXPIRED","1.000000");
        });
        scanner.scan();assertEquals(99L,TenantContextHolder.getTenantId());assertTrue(TenantContextHolder.isIgnore());
        verify(service).expire(second);
    }
    @Test void boundedCursorAdvancesPastFailedFirstPageAndWrapsToRetry() {
        config.setBatchSize(1);config.setMaxBatches(1);
        var first=candidate(1,10);var second=candidate(2,10);
        when(mapper.scanExpired(any(),any(),anyLong(),eq(1))).thenReturn(List.of(first),List.of(second),List.of(),List.of(first));
        when(service.expire(any())).thenThrow(new IllegalStateException("failure"));
        scanner.scan();scanner.scan();scanner.scan();scanner.scan();
        var ids=ArgumentCaptor.forClass(Long.class);
        verify(mapper,times(4)).scanExpired(any(),any(),ids.capture(),eq(1));
        assertEquals(List.of(0L,1L,2L,0L),ids.getAllValues());verify(service,times(2)).expire(first);verify(service).expire(second);
    }
    @Test void singleTickCannotExceedConfiguredBatchBudget() {
        config.setBatchSize(1);config.setMaxBatches(2);
        when(mapper.scanExpired(any(),any(),anyLong(),eq(1))).thenReturn(List.of(candidate(1,10)),List.of(candidate(2,10)));
        when(service.expire(any())).thenReturn(new FulExpiryService.ExpiryResult("1","ALREADY_CLOSED","0.000000"));
        scanner.scan();verify(mapper,times(2)).scanExpired(any(),any(),anyLong(),eq(1));verify(service,times(2)).expire(any());
    }
    @Test void disabledTenantDoesNotInvokeBusinessCommandOrLeakContext() {
        var r=candidate(1,10);when(mapper.scanExpired(any(),any(),anyLong(),anyInt())).thenReturn(List.of(r),List.of());
        doThrow(new IllegalStateException("tenant disabled")).when(tenants).validTenant(10L);
        scanner.scan();verifyNoInteractions(service);assertNull(TenantContextHolder.getTenantId());assertFalse(TenantContextHolder.isIgnore());
    }
    @Test void futureCandidateCanBeRetriedAfterEndOfScan() {
        var r=candidate(1,10);config.setMaxBatches(1);
        when(mapper.scanExpired(any(),any(),anyLong(),anyInt())).thenReturn(List.of(r),List.of(),List.of(r));
        when(service.expire(r)).thenThrow(new FulExpiryService.CandidateNotDueException())
                .thenReturn(new FulExpiryService.ExpiryResult("1","EXPIRED","1.000000"));
        scanner.scan();scanner.scan();scanner.scan();verify(service,times(2)).expire(r);assertNull(TenantContextHolder.getTenantId());
    }
}
