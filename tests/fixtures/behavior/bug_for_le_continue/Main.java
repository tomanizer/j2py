public class Main {
    public static void main(String[] args) {
        // Sum 1..5, skipping 3. Expected: 1+2+4+5 = 12
        // Rule layer: i <= 5 doesn't match range-loop (only < is detected), so it
        // falls back to a while loop where `continue` skips the i++ increment → infinite loop.
        int total = 0;
        for (int i = 1; i <= 5; i++) {
            if (i == 3) continue;
            total += i;
        }
        System.out.println(total);
    }
}
