import java.util.ArrayList;
import java.util.List;
public class Main {
    public static void main(String[] args) {
        List<Integer> xs = new ArrayList<>();
        for (int i = 1; i <= 5; i++) { xs.add(i * i); }
        int total = 0;
        for (int x : xs) { total += x; }
        System.out.println(total);
        System.out.println(xs.size());
    }
}
