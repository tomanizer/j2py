public class Main {
    int sumSquares(int n) {
        int total = 0;
        for (int i = 1; i <= n; i++) { total += i * i; }
        return total;
    }
    public static void main(String[] args) {
        Main m = new Main();
        System.out.println(m.sumSquares(5));
        System.out.println(m.sumSquares(10));
    }
}
