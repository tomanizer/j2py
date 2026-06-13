public class Main {
    void repeat(String s, int n) {
        for (int i = 0; i < n; i++) { System.out.println(s); }
    }
    public static void main(String[] args) {
        Main m = new Main();
        m.repeat("echo", 3);
    }
}
