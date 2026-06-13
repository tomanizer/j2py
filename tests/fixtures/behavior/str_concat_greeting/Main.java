public class Main {
    String greet(String name, int times) {
        return "hi " + name + " x" + times;
    }
    public static void main(String[] args) {
        Main m = new Main();
        System.out.println(m.greet("bob", 3));
    }
}
