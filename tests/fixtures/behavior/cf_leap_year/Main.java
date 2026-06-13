public class Main {
    String leap(int y) {
        if (y % 4 == 0 && y % 100 != 0 || y % 400 == 0) { return "leap"; }
        return "common";
    }
    public static void main(String[] args) {
        Main m = new Main();
        int[] years = {2000, 1900, 2024, 2023};
        for (int y : years) { System.out.println(m.leap(y)); }
    }
}
