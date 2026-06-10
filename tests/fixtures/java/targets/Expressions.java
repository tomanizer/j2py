package org.springframework.core;

public class Expressions {

    public Class<?> choose(Class<?> type, String[] values) {
        Class<?> fallback = Expressions.class;
        return (type != null && values.length > 0) ? type : fallback;
    }

    public String firstOrDefault(String[] values) {
        return !values[0].isEmpty() ? values[0] : "default";
    }
}
