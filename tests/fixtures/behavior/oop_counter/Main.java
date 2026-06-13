public class Main {
    private int value = 0;
    void increment() { this.value++; }
    void reset() { this.value = 0; }
    int get() { return this.value; }
    public static void main(String[] args) {
        Main c = new Main();
        for (int i = 0; i < 7; i++) { c.increment(); }
        System.out.println(c.get());
        c.reset();
        System.out.println(c.get());
    }
}
