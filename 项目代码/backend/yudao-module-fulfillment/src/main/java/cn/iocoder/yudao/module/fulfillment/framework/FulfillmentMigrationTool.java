package cn.iocoder.yudao.module.fulfillment.framework;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.flywaydb.core.Flyway;
import java.sql.*;
import java.util.*;

/** Explicit, non-Spring migration entry. Never cleans a database. */
public final class FulfillmentMigrationTool {
    public static void main(String[] args) throws Exception {
        if (args.length != 1 || !Set.of("baseline", "migrate", "validate").contains(args[0])) {
            throw new IllegalArgumentException("Expected baseline | migrate | validate");
        }
        String db = env("DB_NAME", "fulfillment");
        if (!db.matches("fulfillment(?:_[A-Za-z0-9_]+)?")) throw new IllegalArgumentException("Project database required");
        DriverManagerDataSource source = new DriverManagerDataSource();
        source.setUrl("jdbc:mysql://" + env("DB_HOST", "127.0.0.1") + ":" + env("DB_PORT", "33306")
                + "/" + db + "?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=UTC");
        source.setUsername(env("DB_USER", "fulfillment"));
        source.setPassword(env("DB_PASSWORD", "fulfillment-dev"));
        Flyway flyway = FulfillmentFlywayConfiguration.configure(source);
        switch (args[0]) {
            case "baseline" -> {
                verifyM0(source);
                flyway.baseline();
            }
            case "migrate" -> flyway.migrate();
            case "validate" -> flyway.validate();
            default -> throw new IllegalStateException();
        }
        System.out.println("FULFILLMENT_MIGRATION_OK " + db + " " + args[0]);
    }

    private static String env(String key, String fallback) { return System.getenv().getOrDefault(key, fallback); }

    private static void verifyM0(DriverManagerDataSource source) throws Exception {
        Map<String, List<String>> expected;
        try (var input = FulfillmentMigrationTool.class.getResourceAsStream("/m0-baseline.json")) {
            expected = new ObjectMapper().readValue(input, new TypeReference<>() {});
        }
        try (Connection c = source.getConnection()) {
            Map<String, Set<String>> actual = new TreeMap<>();
            try (var p = c.prepareStatement("SELECT TABLE_NAME,COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE()")) {
                try (var rs=p.executeQuery()) {
                    while(rs.next()) actual.computeIfAbsent(rs.getString(1), k -> new TreeSet<>()).add(rs.getString(2));
                }
            }
            if (!actual.keySet().equals(expected.keySet())) throw new IllegalStateException("M0 table set mismatch; baseline refused: " + actual.keySet());
            for (var e : expected.entrySet()) {
                if (!actual.get(e.getKey()).equals(new TreeSet<>(e.getValue()))) {
                    throw new IllegalStateException("M0 columns mismatch; baseline refused: " + e.getKey());
                }
            }
            // The M0 ERP quantity contract is stronger than matching column names.
            try (var p=c.prepareStatement("SELECT TABLE_NAME,COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME LIKE 'erp\\_%' AND DATA_TYPE='decimal' AND (NUMERIC_PRECISION<>24 OR NUMERIC_SCALE<>6)")) {
                try (var rs=p.executeQuery()) {
                    if(rs.next()) throw new IllegalStateException("M0 decimal contract mismatch: " + rs.getString(1)+"."+rs.getString(2));
                }
            }
        }
    }
}
