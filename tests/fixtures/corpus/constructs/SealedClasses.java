package org.springframework.example;

/**
 * Minimal example for sealed classes (Java 17+).
 * Sealed, non-sealed, permits clauses.
 * Appears in modern Spring for controlled hierarchies (e.g., result types, events).
 */
public sealed interface SealedClasses permits Success, Failure, Pending {

    record Success(String value) implements SealedClasses {}

    record Failure(String error, int code) implements SealedClasses {}

    final class Pending implements SealedClasses {
        private final String id;

        public Pending(String id) {
            this.id = id;
        }

        public String getId() {
            return id;
        }
    }

    // non-sealed subclass allowed
    non-sealed static class ExtendedPending extends Pending {
        public ExtendedPending(String id) {
            super(id);
        }
    }

    static SealedClasses ofValue(String v) {
        return new Success(v);
    }
}
