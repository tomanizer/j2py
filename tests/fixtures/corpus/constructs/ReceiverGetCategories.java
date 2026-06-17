package org.springframework.example;

import java.util.BitSet;
import java.util.List;
import java.util.Map;

/**
 * Receiver-aware get() lowering across list, map, and indexed-predicate categories.
 */
public class ReceiverGetCategories {
    private BitSet bitSet;

    public String listValue(List<String> values, int index) {
        return values.get(index);
    }

    public Object mapValue(Map<String, Object> values, String key) {
        return values.get(key);
    }

    public boolean bitSetValue(int index) {
        return bitSet.get(index);
    }
}
