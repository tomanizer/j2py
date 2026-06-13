public class Main {
    String check(int age) {
        if (age < 0) { return "invalid"; }
        if (age < 18) { return "minor"; }
        if (age < 65) { return "adult"; }
        return "senior";
    }
    public static void main(String[] args) {
        Main m = new Main();
        int[] ages = {-1, 10, 30, 70};
        for (int a : ages) { System.out.println(m.check(a)); }
    }
}
