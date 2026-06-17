import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class Main {
    List<Integer> orderedScores() {
        List<Integer> scores = new ArrayList<>();
        scores.add(12);
        scores.add(7);
        scores.add(19);
        scores.add(7);
        Collections.sort(scores);
        return scores;
    }

    int middleScore(List<Integer> scores) {
        return scores.get(scores.size() / 2);
    }

    String hasScore(List<Integer> scores, int value) {
        return scores.contains(value) ? "present" : "missing";
    }

    public static void main(String[] args) {
        Main demo = new Main();
        List<Integer> scores = demo.orderedScores();
        System.out.println(scores.size());
        System.out.println(demo.middleScore(scores));
        System.out.println(demo.hasScore(scores, 12));
        for (int score : scores) {
            System.out.println(score);
        }
    }
}
