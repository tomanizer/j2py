public class Main {
    int absDiff(int a, int b) { return Math.abs(a - b); }
    public static void main(String[] args) {
        Main m = new Main();
        System.out.println(m.absDiff(3, 10));
        System.out.println(m.absDiff(10, 3));
    }
}
