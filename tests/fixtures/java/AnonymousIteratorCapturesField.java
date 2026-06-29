import java.util.NoSuchElementException;

public class AnonymousIteratorCapturesField {
    private final String[] values;
    private int offset;

    public AnonymousIteratorCapturesField(String[] values, int offset) {
        this.values = values;
        this.offset = offset;
    }

    public Object iterator() {
        return new Iterator<String>() {
            private int index = offset;

            @Override
            public boolean hasNext() {
                return index < values.length;
            }

            @Override
            public String next() {
                if (index >= values.length) {
                    throw new NoSuchElementException();
                }
                return values[index++];
            }
        };
    }
}
