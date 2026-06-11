package org.springframework.example;

/**
 * Minimal example for records with additional features.
 * Compact constructors, accessors, implementing interfaces.
 * Increasingly used in Spring for DTOs, events, configuration records.
 */
public record ComplexRecords(String id, int version, String payload)
        implements java.io.Serializable {

    // Compact constructor with validation
    public ComplexRecords {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id must not be blank");
        }
        if (version < 0) {
            version = 0;
        }
        payload = payload == null ? "" : payload.trim();
    }

    // Custom accessor
    public String id() {
        return id.toUpperCase();
    }

    public boolean isCurrent() {
        return version > 0;
    }

    // Static factory
    public static ComplexRecords of(String id, int version) {
        return new ComplexRecords(id, version, null);
    }
}
