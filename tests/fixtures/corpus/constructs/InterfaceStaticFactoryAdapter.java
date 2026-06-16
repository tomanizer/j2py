package org.springframework.example;

public interface InterfaceStaticFactoryAdapter<T> {
    void apply(T value);

    static <U> InterfaceStaticFactoryAdapter<U> empty() {
        return value -> {};
    }
}
