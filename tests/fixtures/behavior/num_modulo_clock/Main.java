public class Main {
    int addHours(int start, int delta) {
        int raw = start + delta;
        return raw % 12;
    }
    public static void main(String[] args) {
        Main m = new Main();
        System.out.println(m.addHours(10, 5));
        System.out.println(m.addHours(3, 24));
    }
}
