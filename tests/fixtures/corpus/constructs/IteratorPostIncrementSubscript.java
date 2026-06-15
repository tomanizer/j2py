package com.fasterxml.jackson.example;

/**
 * Corpus hotspot: Jackson ArrayIterator generated invalid Python for a post-increment
 * expression inside an array subscript.
 */
public class IteratorPostIncrementSubscript<T> {
    private final T[] values;
    private int index;

    public IteratorPostIncrementSubscript(T[] values) {
        this.values = values;
        this.index = 0;
    }

    public T next() {
        return values[index++];
    }
}
