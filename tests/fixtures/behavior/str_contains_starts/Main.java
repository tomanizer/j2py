public class Main {
    public static void main(String[] args) {
        String s = "hello world";
        System.out.println(s.contains("world") ? "has" : "missing");
        System.out.println(s.startsWith("hello") ? "starts" : "no");
        System.out.println(s.equals("hello world") ? "eq" : "ne");
    }
}
