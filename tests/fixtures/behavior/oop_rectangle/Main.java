public class Main {
    private final int width;
    private final int height;
    Main(int width, int height) { this.width = width; this.height = height; }
    int area() { return this.width * this.height; }
    int perimeter() { return 2 * this.width + 2 * this.height; }
    public static void main(String[] args) {
        Main r = new Main(4, 6);
        System.out.println(r.area());
        System.out.println(r.perimeter());
    }
}
