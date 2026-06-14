public class Main {
    static class Accumulator {
        private int total = 0;

        public void add(int n) {
            total += n;
        }

        public int result() {
            return total;
        }
    }

    public static void main(String[] args) {
        Accumulator acc = new Accumulator();
        acc.add(10);
        acc.add(5);
        // Expected: 15; user-defined add(n) must not be lowered to append(n).
        System.out.println(acc.result());
    }
}
