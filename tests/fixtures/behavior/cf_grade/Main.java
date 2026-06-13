public class Main {
    String grade(int score) {
        if (score >= 90) { return "A"; }
        else if (score >= 80) { return "B"; }
        else if (score >= 70) { return "C"; }
        else { return "F"; }
    }
    public static void main(String[] args) {
        Main m = new Main();
        int[] scores = {95, 83, 71, 50};
        for (int s : scores) { System.out.println(m.grade(s)); }
    }
}
