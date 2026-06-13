import java.util.ArrayList;
import java.util.List;
public class Main {
    private final List<Integer> items = new ArrayList<>();
    void push(int x) { this.items.add(x); }
    int depth() { return this.items.size(); }
    int peek() {
        int last = this.items.size() - 1;
        return this.items.get(last);
    }
    public static void main(String[] args) {
        Main s = new Main();
        s.push(10); s.push(20); s.push(30);
        System.out.println(s.depth());
        System.out.println(s.peek());
    }
}
