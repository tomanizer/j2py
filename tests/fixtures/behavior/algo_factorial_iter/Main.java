public class Main {
    int factorial(int n) {
        int result = 1;
        for (int i = 2; i <= n; i++) { result = result * i; }
        return result;
    }
    public static void main(String[] args) {
        Main m = new Main();
        System.out.println(m.factorial(6));
    }
}
