public class Main {
    private final int x;
    private final int y;
    Main(int x, int y) { this.x = x; this.y = y; }
    int manhattan(Main other) { return Math.abs(this.x - other.x) + Math.abs(this.y - other.y); }
    String show() { return "(" + this.x + "," + this.y + ")"; }
    public static void main(String[] args) {
        Main a = new Main(1, 2);
        Main b = new Main(4, 6);
        System.out.println(a.show());
        System.out.println(a.manhattan(b));
    }
}
