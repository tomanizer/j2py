public class Main {
    int countEvens(int[] a) {
        int count = 0;
        for (int x : a) {
            if (x % 2 == 0) { count++; }
        }
        return count;
    }
    public static void main(String[] args) {
        Main m = new Main();
        int[] a = {1, 2, 3, 4, 5, 6};
        System.out.println(m.countEvens(a));
    }
}
