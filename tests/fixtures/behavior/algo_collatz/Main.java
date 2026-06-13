public class Main {
    int steps(int n) {
        int count = 0;
        while (n != 1) {
            if (n % 2 == 0) { n = n - n / 2; } else { n = 3 * n + 1; }
            count++;
        }
        return count;
    }
    public static void main(String[] args) {
        Main m = new Main();
        System.out.println(m.steps(6));
    }
}
