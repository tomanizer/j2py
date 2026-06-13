package com.example;

/**
 * Normalizes input strings for review.
 *
 * <p>References {@link #normalize(String)} and {@link #normalize(String, Object)} values.
 *
 * @since 1.0
 */
public class JavadocConversion {

    /**
     * Normalize the supplied value.
     *
     * @param value the raw value to normalize
     * @return the normalized value
     * @throws IllegalArgumentException when value is invalid
     */
    public String normalize(String value) {
        return value;
    }

    /**
     * Clean a value.
     *
     * @deprecated use {@link #normalize(String)} instead.
     * @param value the raw value
     * @return the cleaned value
     */
    public String clean(String value) {
        return normalize(value);
    }
}
