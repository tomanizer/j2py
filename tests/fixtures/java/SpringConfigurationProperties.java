package example;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
class AppConfig {
    private String datasourceUrl = "jdbc:h2:mem:testdb";
    private int maxConnections = 10;
}

class ValueConsumer {
    @Value("${app.cache-seconds:512}")
    private int cacheSeconds;

    @Value("${app.welcome-message:Welcome}")
    private String welcomeMessage;
}
