public class Main {
    int total(int[] a) {
        int acc = 0;
        for (int i = 0; i < a.length; i++) { acc += a[i]; }
        return acc;
    }
    public static void main(String[] args) {
        Main m = new Main();
        int[] a = {4, 8, 15, 16, 23, 42};
        System.out.println(m.total(a));
    }
}
