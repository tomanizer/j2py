package org.apache.commons.lang3.example;

/**
 * Corpus hotspot: Commons Lang CachedRandomBits contains an assert_statement in a
 * normal method body.
 */
public class CorpusAssertStatementProbe {

    public void refill(int bitIndex, byte[] cache) {
        assert bitIndex == cache.length * 8;
    }
}
