package org.springframework.example;

/**
 * Minimal Spring-style dependency injection patterns for corpus coverage.
 *
 * Uses local annotation stubs so the file stays self-contained (no Spring JAR).
 * Exercises stereotype annotations, @Configuration/@Bean, constructor injection,
 * and field injection with @Qualifier.
 */
@interface Autowired {}

@interface Service {}

@interface Repository {}

@interface Configuration {}

@interface Bean {
    String value() default "";
}

@interface Qualifier {
    String value();
}

interface PaymentGateway {}

interface DataSource {}

@Configuration
public class SpringDependencyInjection {

    @Bean
    public OrderService orderService(PaymentGateway gateway) {
        return new OrderService(gateway);
    }

    @Service
    static class OrderService {
        private final PaymentGateway gateway;

        @Autowired
        OrderService(PaymentGateway gateway) {
            this.gateway = gateway;
        }

        PaymentGateway gateway() {
            return gateway;
        }
    }

    @Repository
    static class JdbcOrderRepository {
        @Autowired
        @Qualifier("primary")
        private DataSource dataSource;

        DataSource dataSource() {
            return dataSource;
        }
    }
}
