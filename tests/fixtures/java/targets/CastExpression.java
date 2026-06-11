package org.springframework.core;

public class CastExpression {

    public String canonicalName(Object value) {
        return ((TypeReference) value).getCanonicalName();
    }
}
