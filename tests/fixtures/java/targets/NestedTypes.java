package org.springframework.aot.generate;

public class NestedTypes {

    public interface Writer {
        void write(String value);
    }

    public interface Labelled {
        String label();
    }

    public enum Mode implements Labelled {
        FAST("fast", 1),
        SAFE("safe", 2);

        private final String displayName;
        private final int sortOrder;

        Mode(String displayName, int sortOrder) {
            this.displayName = displayName;
            this.sortOrder = sortOrder;
        }

        @Override
        public String label() {
            return displayName;
        }

        public int order() {
            return sortOrder;
        }
    }

    public record Entry(String name, int order) {
    }

    public static class Builder {
        public Entry build(String name) {
            return new Entry(name, 1);
        }
    }
}
