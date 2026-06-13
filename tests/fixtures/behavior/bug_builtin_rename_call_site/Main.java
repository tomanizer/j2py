public class Main {
    static class Stats {
        // Method named 'sum' collides with Python builtin.
        // Rule layer renames the def to sum_() but call site stays .sum() → AttributeError.
        public int sum(int a, int b) {
            return a + b;
        }
    }

    public static void main(String[] args) {
        Stats s = new Stats();
        System.out.println(s.sum(3, 4));
    }
}
