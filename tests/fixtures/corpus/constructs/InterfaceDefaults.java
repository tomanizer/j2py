package org.springframework.example;

import java.util.function.Consumer;

/**
 * Minimal example exercising interface default methods and static methods.
 * Common in Spring for callback interfaces, listeners, and utility interfaces.
 */
public interface InterfaceDefaults<T> extends Consumer<T> {

    // Abstract method (must be implemented)
    void handle(T value);

    // Default method (provides implementation)
    default void accept(T value) {
        if (value != null) {
            handle(value);
        } else {
            handleDefault();
        }
    }

    // Another default with logic
    default void handleDefault() {
        System.out.println("default handling");
    }

    // Static method on interface
    static <U> InterfaceDefaults<U> noop() {
        return v -> {};
    }

    // Static factory
    static <U> InterfaceDefaults<U> logging(Consumer<U> delegate) {
        return v -> {
            System.out.println("logging: " + v);
            delegate.accept(v);
        };
    }
}
