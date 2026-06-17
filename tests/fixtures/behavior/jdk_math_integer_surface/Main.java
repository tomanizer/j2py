public class Main {
    int spread(String left, String right) {
        int a = Integer.parseInt(left);
        int b = Integer.parseInt(right);
        return Math.max(a, b) - Math.min(a, b);
    }

    int boundedDistance(int value, int target, int limit) {
        int distance = Math.abs(value - target);
        return Math.min(distance, limit);
    }

    public static void main(String[] args) {
        Main demo = new Main();
        System.out.println(demo.spread("-12", "7"));
        System.out.println(demo.boundedDistance(42, 15, 20));
        System.out.println(demo.boundedDistance(42, 15, 99));
    }
}
