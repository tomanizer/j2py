class Stats {
    public int sum(int a, int b) {
        return a + b;
    }
}

public class Main {
    public static void main(String[] args) {
        Stats stats = new Stats();
        System.out.println(stats.sum(3, 4));
    }
}
