public class Main {
    int factorial(int n) {
        if (n <= 1) { return 1; }
        return n * this.factorial(n - 1);
    }
    public static void main(String[] args) {
        Main m = new Main();
        System.out.println(m.factorial(7));
    }
}
