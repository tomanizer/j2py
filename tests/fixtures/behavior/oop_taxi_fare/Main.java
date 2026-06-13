public class Main {
    private final int baseFare;
    private final int perMile;
    Main(int baseFare, int perMile) { this.baseFare = baseFare; this.perMile = perMile; }
    int fare(int miles) { return this.baseFare + this.perMile * miles; }
    public static void main(String[] args) {
        Main cab = new Main(3, 2);
        System.out.println(cab.fare(0));
        System.out.println(cab.fare(10));
    }
}
