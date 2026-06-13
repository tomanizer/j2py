public class Main {
    public static void main(String[] args) {
        int a = 3;
        int b = 4;
        // Parentheses must be preserved: (3 + 4) * 2 = 14, not 3 + (4 * 2) = 11
        int result = (a + b) * 2;
        System.out.println(result);
    }
}
