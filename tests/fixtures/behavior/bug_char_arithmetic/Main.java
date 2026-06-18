public class Main {
    static char next(char value) {
        return (char) (value + 1);
    }

    static int distance(char left, char right) {
        return right - left;
    }

    static boolean isControl(char value) {
        return value < 32;
    }

    public static void main(String[] args) {
        System.out.println(next('a'));
        System.out.println(distance('a', 'd'));
        System.out.println(isControl('\n') ? 1 : 0);
        System.out.println(isControl('A') ? 1 : 0);
    }
}
