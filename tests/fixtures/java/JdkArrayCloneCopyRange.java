import java.util.Arrays;

public class JdkArrayCloneCopyRange {
    private final String[] values;

    public JdkArrayCloneCopyRange(String[] values) {
        this.values = values.clone();
    }

    public String[] remaining(int offset) {
        return Arrays.copyOfRange(values, offset, values.length);
    }
}
