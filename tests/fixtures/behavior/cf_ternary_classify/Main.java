public class Main {
    public static void main(String[] args) {
        for (int i = 0; i < 5; i++) {
            String label = i % 2 == 0 ? "even" : "odd";
            System.out.println("n " + i + " " + label);
        }
    }
}
