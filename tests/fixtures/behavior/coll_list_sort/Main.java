import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
public class Main {
    public static void main(String[] args) {
        List<Integer> xs = new ArrayList<>();
        xs.add(5); xs.add(1); xs.add(4); xs.add(2); xs.add(3);
        Collections.sort(xs);
        for (int x : xs) { System.out.println(x); }
    }
}
