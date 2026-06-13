interface Shape { int area(); }
class Square implements Shape {
    private final int side;
    Square(int side) { this.side = side; }
    public int area() { return this.side * this.side; }
}
class Rect implements Shape {
    private final int w;
    private final int h;
    Rect(int w, int h) { this.w = w; this.h = h; }
    public int area() { return this.w * this.h; }
}
public class Main {
    public static void main(String[] args) {
        Shape a = new Square(5);
        Shape b = new Rect(3, 4);
        System.out.println(a.area());
        System.out.println(b.area());
    }
}
