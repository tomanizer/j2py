public class Main {
    int plus(int a, int b) { return a + b; }
    int minus(int a, int b) { return a - b; }
    int times(int a, int b) { return a * b; }
    public static void main(String[] args) {
        Main c = new Main();
        System.out.println(c.plus(3, 4));
        System.out.println(c.minus(10, 6));
        System.out.println(c.times(5, 5));
    }
}
