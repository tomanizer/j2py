public class Main {
    public static void main(String[] args) {
        // Integer division: 20 / 6 = 3 in Java, so translation must not use Python /=.
        int x = 20;
        x /= 6;
        System.out.println(x);
        int negative = -20;
        negative /= 6;
        System.out.println(negative);
    }
}
