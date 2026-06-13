public class Main {
    public static void main(String[] args) {
        try {
            System.out.println("try");
            throw new RuntimeException("boom");
        } catch (RuntimeException e) {
            System.out.println("catch");
        } finally {
            System.out.println("finally");
        }
    }
}
