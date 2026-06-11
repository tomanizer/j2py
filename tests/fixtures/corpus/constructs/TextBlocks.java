package org.springframework.example;

/**
 * Minimal example for Java text blocks (Java 15+).
 * Used in Spring for SQL, JSON, HTML templates, error messages, etc.
 */
public class TextBlocks {

    public String sql() {
        return """
            SELECT id, name
            FROM users
            WHERE status = 'ACTIVE'
              AND created > ?
            ORDER BY name
            """;
    }

    public String jsonTemplate() {
        String name = "test";
        return """
            {
              "name": "%s",
              "active": true,
              "tags": [
                "a",
                "b"
              ]
            }
            """.formatted(name);
    }

    public String indentedBlock() {
        return """
                This is indented.
                    More indent.
                Back to base.
            """;
    }
}
