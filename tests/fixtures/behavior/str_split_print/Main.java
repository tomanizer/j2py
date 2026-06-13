public class Main {
    public static void main(String[] args) {
        String csv = "alpha,beta,gamma";
        String[] parts = csv.split(",");
        for (String p : parts) { System.out.println(p); }
        System.out.println(parts.length);
    }
}
