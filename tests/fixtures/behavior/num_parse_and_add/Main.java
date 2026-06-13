public class Main {
    public static void main(String[] args) {
        String[] tokens = {"10", "20", "30"};
        int total = 0;
        for (String t : tokens) { total += Integer.parseInt(t); }
        System.out.println(total);
    }
}
