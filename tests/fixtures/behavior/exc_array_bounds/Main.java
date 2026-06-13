public class Main {
    public static void main(String[] args) {
        int[] a = {1, 2, 3};
        try {
            int x = a[10];
            System.out.println(x);
        } catch (ArrayIndexOutOfBoundsException e) {
            System.out.println("out of bounds");
        }
        System.out.println("done");
    }
}
