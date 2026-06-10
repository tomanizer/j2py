package org.springframework.aot.generate;

public class NestedTypes {

    public interface Writer {
        void write(String value);
    }

    public enum Mode {
        FAST,
        SAFE
    }

    public record Entry(String name, int order) {
    }

    public static class Builder {
        public Entry build(String name) {
            return new Entry(name, 1);
        }
    }
}
