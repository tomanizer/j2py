public class Main {
    int triangular(int n) {
        int total = 0;
        for (int i = 1; i <= n; i++) { total += i; }
        return total;
    }
    public static void main(String[] args) {
        Main m = new Main();
        for (int n = 1; n <= 5; n++) { System.out.println(m.triangular(n)); }
    }
}
