public class Main {
    public static void main(String[] args) {
        int n = 1, product = 1;
        do {
            product = product * n;
            n++;
        } while (n <= 5);
        System.out.println(product);
    }
}
