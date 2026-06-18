public class Main {
    static int shiftInt(int value, int distance) {
        return value >>> distance;
    }

    static long shiftLong(long value, int distance) {
        return value >>> distance;
    }

    public static void main(String[] args) {
        System.out.println(shiftInt(-2, 1));
        System.out.println(shiftInt(-1, 4));
        System.out.println(shiftLong(-2L, 1));
        System.out.println(shiftLong(-1L, 4));
    }
}
