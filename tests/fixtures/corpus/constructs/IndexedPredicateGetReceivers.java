package org.springframework.example;

import java.util.BitSet;

/**
 * Indexed predicate get() receivers (e.g. BitSet) stay method calls, not [] access.
 */
public class IndexedPredicateGetReceivers {
    private BitSet bitSet;

    public boolean isSet(int index) {
        return this.bitSet.get(index);
    }

    public boolean fromParam(BitSet flags, int index) {
        return flags.get(index);
    }
}
