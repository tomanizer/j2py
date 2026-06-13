public class Main {
    int gcd(int a, int b) {
        while (b != 0) {
            int t = b;
            b = a % b;
            a = t;
        }
        return a;
    }
    public static void main(String[] args) {
        Main m = new Main();
        System.out.println(m.gcd(48, 36));
        System.out.println(m.gcd(17, 5));
    }
}
