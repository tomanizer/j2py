public class Main {
    public int sumTo(int limit) {
        int total = 0;
        for (int index = 0; index < limit; index++) {
            total += index;
        }
        return total;
    }

    public static void main(String[] args) {
        Main sample = new Main();
        System.out.println(sample.sumTo(5));
    }
}
