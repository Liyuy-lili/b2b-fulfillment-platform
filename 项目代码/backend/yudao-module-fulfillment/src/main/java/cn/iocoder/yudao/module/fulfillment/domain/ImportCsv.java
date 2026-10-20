package cn.iocoder.yudao.module.fulfillment.domain;

import java.io.*;
import java.nio.charset.*;
import java.nio.file.*;
import java.util.*;

/** UTF-8 RFC4180 subset: bounded fields, quoted delimiters/newlines and doubled quotes. */
public final class ImportCsv implements AutoCloseable {
    public static final List<String> HEADER=List.of("externalOrderNo","customerCode","productCode","quantity","unitPrice");
    public record Row(int number,List<String> fields,boolean oversized) {}
    public static class InvalidCsv extends IOException {public InvalidCsv(String message){super(message);}}
    private final PushbackReader reader;private int number;private boolean oversized;
    public ImportCsv(InputStream stream)throws IOException {
        reader=new PushbackReader(new BufferedReader(new InputStreamReader(stream,StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT).onUnmappableCharacter(CodingErrorAction.REPORT)),65536),2);
        try{
            int first=reader.read();if(first!=-1&&first!=0xfeff)reader.unread(first);
            List<String> header=record();
            if(header==null||oversized||!header.equals(HEADER))throw new InvalidCsv("CSV_HEADER_V1_REQUIRED");
        }catch(IOException|RuntimeException failure){
            try{reader.close();}catch(IOException closeFailure){failure.addSuppressed(closeFailure);}throw failure;
        }
    }
    public Row next()throws IOException {List<String> fields=record();return fields==null?null:new Row(++number,List.copyOf(fields),oversized);}
    private List<String> record()throws IOException {
        oversized=false;List<String> fields=new ArrayList<>();StringBuilder field=new StringBuilder();boolean quoted=false,closed=false,start=true,any=false;
        while(true){
            int n=reader.read();if(n==-1){if(quoted)throw new InvalidCsv("CSV_UNCLOSED_QUOTE");if(!any&&fields.isEmpty()&&field.isEmpty())return null;add(fields,field);return fields;}
            any=true;char c=(char)n;if(c==0)throw new InvalidCsv("CSV_NUL_NOT_ALLOWED");
            if(quoted){
                if(c=='"'){int next=reader.read();if(next=='"')append(field,'"');else{quoted=false;closed=true;if(next!=-1)reader.unread(next);}}
                else append(field,c);continue;
            }
            if(c==','||c=='\r'||c=='\n'){
                add(fields,field);field.setLength(0);start=true;closed=false;
                if(c!=','){if(c=='\r'){int next=reader.read();if(next!='\n'&&next!=-1)reader.unread(next);}return fields;}
                continue;
            }
            if(closed)throw new InvalidCsv("CSV_CHAR_AFTER_QUOTE");
            if(c=='"'){if(!start)throw new InvalidCsv("CSV_QUOTE_INSIDE_UNQUOTED_FIELD");quoted=true;start=false;}
            else{append(field,c);start=false;}
        }
    }
    private void append(StringBuilder field,char c){if(field.length()<256)field.append(c);else oversized=true;}
    private void add(List<String> fields,StringBuilder field){if(fields.size()<6)fields.add(field.toString());else oversized=true;}
    public static String safeCell(String value){
        String v=value==null?"":value;String first=v.stripLeading();
        if(!first.isEmpty()&&"=+-@".indexOf(first.charAt(0))>=0||v.startsWith("\t")||v.startsWith("\r")||v.startsWith("\n"))v="'"+v;
        return '"'+v.replace("\"","\"\"")+'"';
    }
    @Override public void close()throws IOException{reader.close();}
}
