public class Main {
    public static void main(String[] args) {
        // Sum 1..5, skipping 3. Expected: 1+2+4+5 = 12
        // The inclusive bound must translate to a range loop so continue is safe.
        int total = 0;
        for (int i = 1; i <= 5; i++) {
            if (i == 3) continue;
            total += i;
        }
        System.out.println(total);
    }
}
