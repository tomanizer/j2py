public class Main {
    int safeDivideMod(int a, int b) {
        if (b == 0) { throw new IllegalArgumentException("zero"); }
        return a % b;
    }
    public static void main(String[] args) {
        Main m = new Main();
        try {
            System.out.println(m.safeDivideMod(17, 5));
            System.out.println(m.safeDivideMod(10, 0));
        } catch (IllegalArgumentException e) {
            System.out.println("caught");
        }
    }
}
