public class Main {
    String censor(String s) {
        return s.replace("a", "*").replace("e", "*").replace("i", "*");
    }
    public static void main(String[] args) {
        Main m = new Main();
        System.out.println(m.censor("aerial gaze"));
    }
}
