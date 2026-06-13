public class Main {
    public static void main(String[] args) {
        int[] xs = {3, 1, 4, 1, 5, 9, 2, 6};
        int best = xs[0];
        for (int x : xs) { best = Math.max(best, x); }
        System.out.println(best);
    }
}
