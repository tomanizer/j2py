public class Main {
    public int score(int value) {
        int doubled = value * 2;
        if (doubled > 10) {
            return doubled - 3;
        }
        return doubled + 3;
    }

    public static void main(String[] args) {
        Main sample = new Main();
        System.out.println(sample.score(4));
        System.out.println(sample.score(8));
    }
}
