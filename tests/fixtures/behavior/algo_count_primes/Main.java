public class Main {
    boolean isPrime(int n) {
        if (n < 2) { return false; }
        for (int d = 2; d < n; d++) {
            if (n % d == 0) { return false; }
        }
        return true;
    }
    public static void main(String[] args) {
        Main m = new Main();
        int count = 0;
        for (int i = 0; i < 30; i++) {
            if (m.isPrime(i)) { count++; }
        }
        System.out.println(count);
    }
}
