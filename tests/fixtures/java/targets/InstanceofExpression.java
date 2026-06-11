package org.springframework.core;

public class InstanceofExpression {

    public String label(Object value) {
        if (value instanceof String text) {
            return text.trim();
        }
        return "unknown";
    }
}
