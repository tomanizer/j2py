public class Main {
    String classify(int n) {
        if (n < 2) { return "no"; }
        for (int d = 2; d < n; d++) {
            if (n % d == 0) { return "no"; }
        }
        return "yes";
    }
    public static void main(String[] args) {
        Main m = new Main();
        int[] xs = {1, 2, 9, 13, 15, 17};
        for (int x : xs) { System.out.println(m.classify(x)); }
    }
}
