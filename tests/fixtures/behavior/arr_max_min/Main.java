public class Main {
    public static void main(String[] args) {
        int[] a = {7, 2, 9, 4, 1};
        int max = a[0], min = a[0];
        for (int x : a) {
            if (x > max) { max = x; }
            if (x < min) { min = x; }
        }
        System.out.println(max);
        System.out.println(min);
    }
}
