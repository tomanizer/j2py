public class Main {
    int fib(int n) {
        if (n < 2) { return n; }
        return this.fib(n - 1) + this.fib(n - 2);
    }
    public static void main(String[] args) {
        Main m = new Main();
        for (int i = 0; i < 10; i++) { System.out.println(m.fib(i)); }
    }
}
