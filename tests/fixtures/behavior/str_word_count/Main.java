public class Main {
    int words(String text) {
        String[] parts = text.split(" ");
        return parts.length;
    }
    public static void main(String[] args) {
        Main m = new Main();
        System.out.println(m.words("the quick brown fox"));
    }
}
