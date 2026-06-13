public class Main {
    String tidy(String s) {
        String t = s.trim();
        return t.isEmpty() ? "blank" : t;
    }
    public static void main(String[] args) {
        Main m = new Main();
        System.out.println(m.tidy("   spaced   "));
        System.out.println(m.tidy("    "));
    }
}
