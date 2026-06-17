public class Main {
    String normalize(String raw) {
        return raw.trim().toLowerCase().replace(" ", "-");
    }

    String classify(String raw) {
        String normalized = normalize(raw);
        if (normalized.isEmpty()) {
            return "blank";
        }
        if (normalized.startsWith("alpha") && normalized.contains("beta")) {
            return normalized.toUpperCase();
        }
        return normalized;
    }

    int segmentCount(String raw) {
        String[] parts = raw.trim().split(",");
        return parts.length;
    }

    int normalizedLength(String raw) {
        return normalize(raw).length();
    }

    public static void main(String[] args) {
        Main demo = new Main();
        System.out.println(demo.classify("  Alpha Beta  "));
        System.out.println(demo.classify("   "));
        System.out.println(demo.segmentCount("red,green,blue"));
        System.out.println(demo.normalizedLength("  Two Words  "));
    }
}
