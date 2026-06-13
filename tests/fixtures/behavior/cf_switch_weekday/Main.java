public class Main {
    String name(int d) {
        switch (d) {
            case 1: return "Mon";
            case 2: return "Tue";
            case 3: return "Wed";
            default: return "Other";
        }
    }
    public static void main(String[] args) {
        Main m = new Main();
        for (int i = 1; i <= 4; i++) { System.out.println(m.name(i)); }
    }
}
