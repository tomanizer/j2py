package org.springframework.example;

import java.util.List;

/**
 * Class-keyed registry get() calls should remain API method calls.
 */
public class ClassKeyedRegistryGet {
    public int count(CustomizerRegistry registry) {
        int total = 0;
        for (Customizer customizer : registry.get(Customizer.class)) {
            total += customizer.weight();
        }
        return total;
    }

    static class CustomizerRegistry {
        <T> List<T> get(Class<T> klass) {
            return null;
        }
    }

    interface Customizer {
        int weight();
    }
}
