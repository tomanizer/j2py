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

    public Writer anonymousWriter(String prefix) {
        return new Writer() {
            @Override
            public void write(String value) {
                System.out.println(prefix + value);
            }
        };
    }

    public Object localEntry(String name) {
        class LocalEntry {
            public String value() {
                return name;
            }
        }
        return new LocalEntry();
    }
}
