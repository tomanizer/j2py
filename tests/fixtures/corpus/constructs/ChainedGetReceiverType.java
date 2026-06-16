package org.springframework.example;

import java.lang.reflect.Method;
import java.util.List;

/**
 * Chained get() receivers should use declared method return types.
 */
public class ChainedGetReceiverType {
    private Mapping mapping;

    public Method attribute(int attributeIndex) {
        return this.mapping.getAttributes().get(attributeIndex);
    }

    static class Mapping {
        private List<Method> attributes;

        List<Method> getAttributes() {
            return this.attributes;
        }
    }
}
