class StringBuilder {
    public void addChar(char value) {
    }

    public void addString(Object value) {
    }
}

public class OverloadDispatchProbe {
    public OverloadDispatchProbe append(StringBuilder builder, char value) {
        builder.addChar(value);
        return this;
    }

    public OverloadDispatchProbe append(StringBuilder builder, String value) {
        builder.addString(value);
        return this;
    }
}
