package cn.iocoder.yudao.module.fulfillment.domain;
import org.junit.jupiter.api.Test;
import java.io.*;
import java.nio.charset.StandardCharsets;
import static org.junit.jupiter.api.Assertions.*;
class ImportCsvTest {
    private ImportCsv csv(String rows)throws Exception{return new ImportCsv(new ByteArrayInputStream((String.join(",",ImportCsv.HEADER)+"\r\n"+rows).getBytes(StandardCharsets.UTF_8)));}
    @Test void quotedCommaNewlineAndQuote()throws Exception{try(var c=csv("\"a,b\n\"\"c\",1,SKU,1.000001,2\r\n")){var r=c.next();assertEquals("a,b\n\"c",r.fields().get(0));assertEquals(1,r.number());assertEquals("1.000001",r.fields().get(3));assertNull(c.next());}}
    @Test void bomAndEmptyData()throws Exception{try(var c=new ImportCsv(new ByteArrayInputStream(("\ufeff"+String.join(",",ImportCsv.HEADER)+"\n").getBytes(StandardCharsets.UTF_8)))){assertNull(c.next());}}
    @Test void wrongHeaderRejected(){assertThrows(ImportCsv.InvalidCsv.class,()->new ImportCsv(new ByteArrayInputStream("a,b\n".getBytes())));}
    @Test void unclosedQuoteRejected()throws Exception{try(var c=csv("\"broken")){assertThrows(ImportCsv.InvalidCsv.class,c::next);}}
    @Test void trailingCharactersRejected()throws Exception{try(var c=csv("\"ok\"bad,1,x,1,2")){assertThrows(ImportCsv.InvalidCsv.class,c::next);}}
    @Test void fieldMemoryBounded()throws Exception{try(var c=csv("a".repeat(10000)+",1,x,1,2")){var r=c.next();assertTrue(r.oversized());assertEquals(256,r.fields().get(0).length());}}
    @Test void invalidUtf8Rejected(){assertThrows(IOException.class,()->new ImportCsv(new ByteArrayInputStream(new byte[]{(byte)0xc3,0x28})));}
    @Test void failedHeaderDecodingClosesOriginalStream(){
        boolean[] closed={false};var stream=new FilterInputStream(new ByteArrayInputStream(new byte[]{(byte)0xc3,0x28})){
            @Override public void close()throws IOException{closed[0]=true;super.close();}
        };
        assertThrows(IOException.class,()->new ImportCsv(stream));assertTrue(closed[0]);
    }
    @Test void formulaAndQuoteProtection(){assertEquals("\"'=SUM(1,2)\"",ImportCsv.safeCell("=SUM(1,2)"));assertEquals("\"'  +2\"",ImportCsv.safeCell("  +2"));assertEquals("\"a\"\"b\"",ImportCsv.safeCell("a\"b"));}
}
