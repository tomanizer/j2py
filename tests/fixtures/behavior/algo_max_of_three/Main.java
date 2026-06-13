public class Main {
    int maxOf(int a, int b, int c) {
        return Math.max(a, Math.max(b, c));
    }
    public static void main(String[] args) {
        Main m = new Main();
        System.out.println(m.maxOf(3, 9, 5));
        System.out.println(m.maxOf(8, 2, 4));
    }
}
