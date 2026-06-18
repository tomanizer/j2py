@interface Configuration {}
@interface Bean {
    String value() default "";
}
@interface Repository {}

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

    DataSource build() {
        return null;
    }
}

@Configuration
class SmokeJdbcConfig {
    private Environment env;

    @Bean
    DataSource dataSource() {
        return DataSourceBuilder.create()
            .url(env.getProperty("app.datasource.url"))
            .username(env.getProperty("app.datasource.username"))
            .build();
    }

    @Bean
    JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }
}

@Repository
class SmokeOwnerRepository {
    private final JdbcTemplate jdbcTemplate;

    SmokeOwnerRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    int renameOwner(String firstName, long id) {
        return jdbcTemplate.update(
            "update owners set first_name = ? where id = ?",
            firstName,
            id);
    }

    String ownerName(long id) {
        return jdbcTemplate.queryForObject(
            "select first_name from owners where id = ?",
            String.class,
            id);
    }
}
