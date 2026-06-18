@interface Configuration {}
@interface Bean {
    String value() default "";
}

interface Environment {
    String getProperty(String key);
}

interface DataSource {}
interface JdbcTemplate {}
interface NamedParameterJdbcTemplate {}
interface PlatformTransactionManager {}
interface DataSourceTransactionManager {}

class DataSourceBuilder {
    static DataSourceBuilder create() {
        return new DataSourceBuilder();
    }

    DataSourceBuilder url(String url) {
        return this;
    }

    DataSourceBuilder username(String username) {
        return this;
    }

    DataSourceBuilder driverClassName(String driverClassName) {
        return this;
    }

    DataSource build() {
        return null;
    }
}

@Configuration
public class SpringJdbcConfiguration {
    private Environment env;

    @Bean
    public DataSource dataSource() {
        return DataSourceBuilder.create()
            .url(env.getProperty("app.datasource.url"))
            .username(env.getProperty("app.datasource.username"))
            .driverClassName(env.getProperty("app.datasource.driver-class-name"))
            .build();
    }

    @Bean("jdbcTemplate")
    public JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }

    @Bean
    public NamedParameterJdbcTemplate namedParameterJdbcTemplate(JdbcTemplate jdbcTemplate) {
        return new NamedParameterJdbcTemplate(jdbcTemplate);
    }

    @Bean
    public PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }
}
