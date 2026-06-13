public class Main {
    int find(int[] a, int target) {
        for (int i = 0; i < a.length; i++) {
            if (a[i] == target) { return i; }
        }
        return -1;
    }
    public static void main(String[] args) {
        Main m = new Main();
        int[] a = {5, 10, 15, 20};
        System.out.println(m.find(a, 15));
        System.out.println(m.find(a, 99));
    }
}
