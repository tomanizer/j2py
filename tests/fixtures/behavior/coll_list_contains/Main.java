import java.util.ArrayList;
import java.util.List;
public class Main {
    public static void main(String[] args) {
        List<String> words = new ArrayList<>();
        words.add("cat"); words.add("dog");
        System.out.println(words.contains("dog") ? "found" : "absent");
        System.out.println(words.contains("fish") ? "found" : "absent");
    }
}
