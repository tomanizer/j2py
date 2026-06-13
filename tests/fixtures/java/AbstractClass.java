public abstract class Shape {
    private String label;

    public abstract double area();

    public abstract double perimeter();

    public String color() {
        return this.label;
    }
}
