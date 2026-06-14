public class Main {
    static class Stats {
        // Method named 'sum' collides with Python builtin.
        // The translated def and call site must use the same escaped name.
        public int sum(int a, int b) {
            return a + b;
        }
    }

    public static void main(String[] args) {
        Stats s = new Stats();
        System.out.println(s.sum(3, 4));
    }
}
