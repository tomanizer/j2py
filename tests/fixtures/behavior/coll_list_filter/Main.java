import java.util.ArrayList;
import java.util.List;
public class Main {
    List<Integer> evens(List<Integer> xs) {
        List<Integer> out = new ArrayList<>();
        for (int x : xs) {
            if (x % 2 == 0) { out.add(x); }
        }
        return out;
    }
    public static void main(String[] args) {
        List<Integer> xs = new ArrayList<>();
        for (int i = 1; i <= 10; i++) { xs.add(i); }
        Main m = new Main();
        List<Integer> result = m.evens(xs);
        for (int x : result) { System.out.println(x); }
    }
}
