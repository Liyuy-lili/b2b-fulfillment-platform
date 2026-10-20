package cn.iocoder.yudao.module.fulfillment.integration;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.HexFormat;
import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;
import static cn.iocoder.yudao.module.fulfillment.enums.FulfillmentErrors.CALLBACK_AUTH_INVALID;
public final class LogisticsSignature {
    public static String sign(String secret,String timestamp,String eventId,byte[] body) {
        try {
            Mac mac=Mac.getInstance("HmacSHA256");mac.init(new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8),"HmacSHA256"));
            mac.update((timestamp+"\n"+eventId+"\n").getBytes(StandardCharsets.UTF_8));return HexFormat.of().formatHex(mac.doFinal(body));
        } catch(java.security.GeneralSecurityException e) { throw new IllegalStateException("HMAC unavailable",e); }
    }
    public static void verify(String secret,String timestamp,String eventId,String signature,byte[] body,Instant now) {
        try {
            if(secret==null || secret.length()<16 || timestamp==null || !timestamp.matches("[0-9]{1,12}") || eventId==null || !eventId.matches("[A-Za-z0-9._:-]{1,128}")
                    || signature==null || !signature.matches("[0-9a-fA-F]{64}") || body.length>8192) throw new IllegalArgumentException();
            if(Math.abs(now.getEpochSecond()-Long.parseLong(timestamp))>300) throw new IllegalArgumentException();
            if(!MessageDigest.isEqual(HexFormat.of().parseHex(sign(secret,timestamp,eventId,body)),HexFormat.of().parseHex(signature))) throw new IllegalArgumentException();
        } catch(IllegalArgumentException e) { throw exception(CALLBACK_AUTH_INVALID); }
    }
}
