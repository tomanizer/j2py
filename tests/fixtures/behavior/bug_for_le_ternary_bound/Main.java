public class Main {
    public static void main(String[] args) {
        int total = 0;
        boolean flag = true;
        for (int i = 0; i <= (flag ? 2 : 3); i++) {
            total += i;
        }
        System.out.println(total);
        total = 0;
        flag = false;
        for (int i = 0; i <= (flag ? 2 : 3); i++) {
            total += i;
        }
        System.out.println(total);
    }
}
