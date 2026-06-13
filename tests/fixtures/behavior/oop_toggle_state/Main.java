public class Main {
    private boolean on = false;
    void flip() { this.on = !this.on; }
    String state() { return this.on ? "ON" : "OFF"; }
    public static void main(String[] args) {
        Main t = new Main();
        System.out.println(t.state());
        t.flip();
        System.out.println(t.state());
        t.flip();
        System.out.println(t.state());
    }
}
