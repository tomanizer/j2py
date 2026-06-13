public class Main {
    public static void main(String[] args) {
        int[] a = {5, 2, 8, 1, 9, 3};
        int n = a.length;
        for (int i = 0; i < n; i++) {
            for (int j = 0; j < n - 1; j++) {
                if (a[j] > a[j + 1]) {
                    int t = a[j];
                    a[j] = a[j + 1];
                    a[j + 1] = t;
                }
            }
        }
        for (int x : a) { System.out.println(x); }
    }
}
