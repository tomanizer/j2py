import java.util.Comparator;

public class JdkComparatorAnonymousClass {
    public Comparator<String> byLength() {
        return new Comparator<String>() {
            @Override
            public int compare(String a, String b) {
                return Integer.compare(a.length(), b.length());
            }
        };
    }
}
