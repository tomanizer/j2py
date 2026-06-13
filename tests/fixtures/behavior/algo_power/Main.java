public class Main {
    int power(int base, int exp) {
        int result = 1;
        for (int i = 0; i < exp; i++) { result = result * base; }
        return result;
    }
    public static void main(String[] args) {
        Main m = new Main();
        System.out.println(m.power(2, 10));
        System.out.println(m.power(3, 4));
    }
}
