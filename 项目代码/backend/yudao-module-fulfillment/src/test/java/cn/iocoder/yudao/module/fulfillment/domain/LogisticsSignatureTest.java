package cn.iocoder.yudao.module.fulfillment.domain;
import cn.iocoder.yudao.module.fulfillment.integration.LogisticsSignature;
import org.junit.jupiter.api.Test;
import java.time.Instant;
import java.nio.charset.StandardCharsets;
import static org.junit.jupiter.api.Assertions.*;
class LogisticsSignatureTest {
    private final String secret="local-logistics-demo-secret-change-before-sharing";
    private final Instant now=Instant.parse("2026-10-18T12:00:00Z");
    private final byte[] body="{\"quantity\":\"1.000001\"}".getBytes(StandardCharsets.UTF_8);
    @Test void exactRawBytesAuthenticate() { String t=String.valueOf(now.getEpochSecond());String s=LogisticsSignature.sign(secret,t,"e1",body);assertDoesNotThrow(()->LogisticsSignature.verify(secret,t,"e1",s,body,now)); }
    @Test void whitespaceChangesRequireNewSignature() { String t=String.valueOf(now.getEpochSecond());String s=LogisticsSignature.sign(secret,t,"e1",body);assertThrows(RuntimeException.class,()->LogisticsSignature.verify(secret,t,"e1",s,"{} ".getBytes(StandardCharsets.UTF_8),now)); }
    @Test void eventHeaderCannotBeSubstituted() { String t=String.valueOf(now.getEpochSecond());String s=LogisticsSignature.sign(secret,t,"e1",body);assertThrows(RuntimeException.class,()->LogisticsSignature.verify(secret,t,"e2",s,body,now)); }
    @Test void oldSignatureExpires() { String t=String.valueOf(now.minusSeconds(301).getEpochSecond());String s=LogisticsSignature.sign(secret,t,"e1",body);assertThrows(RuntimeException.class,()->LogisticsSignature.verify(secret,t,"e1",s,body,now)); }
    @Test void futureTimestampOutsideWindowRejected() { String t=String.valueOf(now.plusSeconds(301).getEpochSecond());String s=LogisticsSignature.sign(secret,t,"e1",body);assertThrows(RuntimeException.class,()->LogisticsSignature.verify(secret,t,"e1",s,body,now)); }
    @Test void malformedOrMissingHeadersBecomeAuthFailure() { assertThrows(RuntimeException.class,()->LogisticsSignature.verify(secret,null,null,null,body,now)); }
}
