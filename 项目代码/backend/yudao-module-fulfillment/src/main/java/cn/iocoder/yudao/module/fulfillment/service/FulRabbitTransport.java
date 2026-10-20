package cn.iocoder.yudao.module.fulfillment.service;
import cn.iocoder.yudao.module.fulfillment.framework.MessageProperties;
import com.rabbitmq.client.*;
import jakarta.annotation.PreDestroy;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicReference;
@Component @RequiredArgsConstructor
public class FulRabbitTransport {
    private final MessageProperties properties;
    private Connection consumerConnection;private Channel consumerChannel;
    public record Delivery(byte[] body,long tag) {}
    private Connection connect(String name)throws IOException,TimeoutException{
        var f=new ConnectionFactory();f.setHost(properties.getHost());f.setPort(properties.getPort());f.setUsername(properties.getUsername());f.setPassword(properties.getPassword());f.setVirtualHost(properties.getVirtualHost());
        f.setAutomaticRecoveryEnabled(false);f.setConnectionTimeout(2000);f.setHandshakeTimeout(3000);f.setChannelRpcTimeout(3000);f.setRequestedHeartbeat(10);f.setShutdownTimeout(1000);
        return f.newConnection(name);
    }
    private void topology(Channel c)throws IOException{
        String n=properties.getNamespace();c.exchangeDeclare(n+".exchange","direct",true);c.exchangeDeclare(n+".dead.exchange","direct",true);
        c.queueDeclare(n+".dead",true,false,false,Map.of("x-queue-type","classic"));c.queueBind(n+".dead",n+".dead.exchange","rejected");
        c.queueDeclare(n+".orders",true,false,false,Map.of("x-queue-type","classic","x-dead-letter-exchange",n+".dead.exchange","x-dead-letter-routing-key","rejected"));c.queueBind(n+".orders",n+".exchange","events");
    }
    /** Returns null only for Broker confirm ACK with no mandatory return. */
    public String publish(FulMessageStore.Claim event)throws Exception{
        try(Connection connection=connect("fulfillment-publisher");Channel channel=connection.createChannel()){
            topology(channel);channel.confirmSelect();var returned=new AtomicReference<String>();
            channel.addReturnListener((code,text,exchange,key,props,body)->returned.set("RETURN_"+code));
            var props=new AMQP.BasicProperties.Builder().deliveryMode(2).contentType("application/json").contentEncoding("UTF-8").messageId(event.eventId()).type("fulfillment-event-v1").build();
            channel.basicPublish(properties.getNamespace()+".exchange",properties.getRoutingKey(),true,props,event.body().getBytes(StandardCharsets.UTF_8));
            boolean ack=channel.waitForConfirms(properties.getConfirmTimeoutMs());
            return returned.get()!=null?returned.get():ack?null:"CONFIRM_NACK";
        }
    }
    public synchronized Delivery receive()throws Exception{
        if(consumerChannel==null||!consumerChannel.isOpen()){
            closeConsumer();consumerConnection=connect("fulfillment-consumer");consumerChannel=consumerConnection.createChannel();topology(consumerChannel);consumerChannel.basicQos(properties.getBatchSize());
        }
        GetResponse response=consumerChannel.basicGet(properties.getNamespace()+".orders",false);
        return response==null?null:new Delivery(response.getBody(),response.getEnvelope().getDeliveryTag());
    }
    public synchronized void ack(long tag)throws IOException{consumerChannel.basicAck(tag,false);}
    public synchronized void reject(long tag)throws IOException{consumerChannel.basicReject(tag,false);}
    @PreDestroy public synchronized void closeConsumer(){
        try{if(consumerChannel!=null)consumerChannel.abort();}catch(Exception ignored){}
        try{if(consumerConnection!=null)consumerConnection.abort();}catch(Exception ignored){}
        consumerChannel=null;consumerConnection=null;
    }
}
