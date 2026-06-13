import java.util.ArrayList;
import java.util.List;
public class Main {
    int maxOf(List<Integer> xs) {
        int best = xs.get(0);
        for (int x : xs) {
            if (x > best) { best = x; }
        }
        return best;
    }
    public static void main(String[] args) {
        List<Integer> xs = new ArrayList<>();
        xs.add(3); xs.add(11); xs.add(7);
        Main m = new Main();
        System.out.println(m.maxOf(xs));
    }
}
