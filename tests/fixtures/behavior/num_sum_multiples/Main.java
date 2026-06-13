public class Main {
    int sumMultiples(int limit) {
        int total = 0;
        for (int i = 0; i < limit; i++) {
            if (i % 3 == 0 || i % 5 == 0) { total += i; }
        }
        return total;
    }
    public static void main(String[] args) {
        Main m = new Main();
        System.out.println(m.sumMultiples(20));
    }
}
