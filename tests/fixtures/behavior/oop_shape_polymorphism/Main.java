import java.util.ArrayList;
import java.util.List;
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
        List<Shape> shapes = new ArrayList<>();
        shapes.add(new Square(2));
        shapes.add(new Rect(3, 4));
        shapes.add(new Square(5));
        int total = 0;
        for (Shape s : shapes) { total += s.area(); }
        System.out.println(total);
    }
}
