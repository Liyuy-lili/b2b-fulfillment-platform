package cn.iocoder.yudao.module.fulfillment.service;

import java.util.*;
import java.sql.*;
import java.time.LocalDateTime;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;

/** Small JDBC conversions shared only by the file-job subsystem. */
public final class JobValues {
    public static long number(Map<String,Object> row,String key){return ((Number)row.get(key)).longValue();}
    public static String text(Map<String,Object> row,String key){return Objects.toString(row.get(key),null);}
    public static boolean flag(Map<String,Object> row,String key){Object v=row.get(key);return Boolean.TRUE.equals(v)||v instanceof Number n&&n.intValue()!=0;}
    public static String time(Object v){return v==null?null:(v instanceof Timestamp t?t.toLocalDateTime():(LocalDateTime)v).toString()+"Z";}
    public static long insert(JdbcTemplate jdbc,String sql,Object...args){
        var keys=new GeneratedKeyHolder();jdbc.update(c->{var s=c.prepareStatement(sql,Statement.RETURN_GENERATED_KEYS);for(int i=0;i<args.length;i++)s.setObject(i+1,args[i]);return s;},keys);
        return Objects.requireNonNull(keys.getKey()).longValue();
    }
    public static String marks(int count){if(count<1)throw new IllegalArgumentException("Empty bounded scope");return String.join(",",Collections.nCopies(count,"?"));}
    public static class LostLease extends RuntimeException {}
    public static class Cancelled extends RuntimeException {}
    public static class PermanentFailure extends RuntimeException {public PermanentFailure(String code){super(code);}}
    public static class RowFailure extends RuntimeException {public RowFailure(String code){super(code);}}
}
