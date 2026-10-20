package cn.iocoder.yudao.module.fulfillment.framework;

import org.flywaydb.core.Flyway;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.beans.factory.SmartInitializingSingleton;
import lombok.extern.slf4j.Slf4j;
import javax.sql.DataSource;

@Configuration
@Slf4j
public class FulfillmentFlywayConfiguration {
    public static Flyway configure(DataSource source) {
        return Flyway.configure().dataSource(source).locations("classpath:db/fulfillment")
                .table("ful_flyway_schema_history").baselineVersion("0")
                .baselineOnMigrate(false).cleanDisabled(true).validateOnMigrate(true)
                .callbacks(new StockMigrationPreflight()).load();
    }

    @Bean(initMethod = "migrate")
    public Flyway fulfillmentFlyway(Environment environment) {
        // Flyway's optional privilege probe can make Druid discard its connection.
        // Migrations use short-lived JDBC connections with exactly the configured DB credentials.
        String prefix="spring.datasource.dynamic.datasource.master.";
        DriverManagerDataSource source=new DriverManagerDataSource(
                environment.getRequiredProperty(prefix+"url"),
                environment.getRequiredProperty(prefix+"username"),
                environment.getRequiredProperty(prefix+"password"));
        return configure(source);
    }

    @Bean
    public SmartInitializingSingleton fulfillmentIsolationCheck(DataSource source) {
        return () -> {
            try (var connection=source.getConnection()) {
                if (connection.getTransactionIsolation()!=java.sql.Connection.TRANSACTION_READ_COMMITTED) {
                    throw new IllegalStateException("Fulfillment requires business datasource READ_COMMITTED (JDBC 2)");
                }
                log.info("Fulfillment business datasource isolation verified: READ_COMMITTED");
                try(var statement=connection.createStatement();var result=statement.executeQuery("SELECT @@innodb_lock_wait_timeout")) {
                    result.next();int timeout=result.getInt(1);
                    if(timeout!=3) throw new IllegalStateException("Fulfillment requires innodb_lock_wait_timeout=3, actual="+timeout);
                    log.info("Fulfillment lock wait timeout verified: {} seconds",timeout);
                }
            } catch (java.sql.SQLException e) { throw new IllegalStateException("Cannot verify business isolation",e); }
        };
    }
}
