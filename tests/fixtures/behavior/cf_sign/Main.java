public class Main {
    String sign(int n) {
        if (n > 0) { return "positive"; }
        else if (n < 0) { return "negative"; }
        else { return "zero"; }
    }
    public static void main(String[] args) {
        Main m = new Main();
        int[] xs = {5, -3, 0};
        for (int x : xs) { System.out.println(m.sign(x)); }
    }
}
