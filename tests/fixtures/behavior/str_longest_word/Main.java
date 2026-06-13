public class Main {
    String longest(String text) {
        String[] parts = text.split(" ");
        String best = "";
        for (String p : parts) {
            if (p.length() > best.length()) { best = p; }
        }
        return best;
    }
    public static void main(String[] args) {
        Main m = new Main();
        System.out.println(m.longest("a bb cccc dd"));
    }
}
