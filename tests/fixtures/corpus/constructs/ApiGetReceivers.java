package org.springframework.example;

import java.nio.ByteBuffer;
import java.util.concurrent.atomic.AtomicLongArray;
import java.util.concurrent.atomic.AtomicReferenceArray;

/**
 * JDK API get() receivers should remain method calls, not collection indexing.
 */
public class ApiGetReceivers {
    private ByteBuffer byteBuffer;
    private AtomicLongArray counts;

    public byte byteAt(int index) {
        return this.byteBuffer.get(index);
    }

    public long countAt(int index) {
        return this.counts.get(index);
    }

    public Object valueAt(AtomicReferenceArray<Object> values, int index) {
        return values.get(index);
    }
}
