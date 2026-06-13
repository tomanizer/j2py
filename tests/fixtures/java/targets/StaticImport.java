import static java.lang.Math.PI;
import static java.lang.Math.abs;
import static java.lang.Math.max;
import static java.lang.Math.sqrt;
import static java.util.Collections.unmodifiableList;

import java.util.List;

public class StaticImport {
    public int distance(int left, int right) {
        return abs(left - right);
    }

    public int larger(int left, int right) {
        return max(left, right);
    }

    public double root(double value) {
        return sqrt(value);
    }

    public double circumference(double radius) {
        return 2 * PI * radius;
    }

    public List<String> immutable(List<String> values) {
        return unmodifiableList(values);
    }
}
