package cn.iocoder.yudao.module.fulfillment.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;
import java.util.*;

@Service @RequiredArgsConstructor
public class FulOperationAudit {
    private final JdbcTemplate jdbc;private final ObjectMapper json;
    public String json(Object value){try{return json.writeValueAsString(value);}catch(Exception e){throw new IllegalStateException("Invalid audit summary",e);}}
    @Transactional(propagation=Propagation.MANDATORY)
    public void add(long tenant,long actor,String operation,String type,String id,String request,String reason,Object before,Object after){
        jdbc.update("INSERT INTO ful_operation_audit(tenant_id,actor_id,operation,object_type,object_id,request_id,reason,before_json,after_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,UTC_TIMESTAMP(6))",
                tenant,actor,operation,type,id,request,reason,json(before),json(after));
    }
}
