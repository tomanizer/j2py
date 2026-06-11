package org.springframework.example;

/**
 * Example exercising switch with intentional fall-through and complex cases.
 * Still a common (if discouraged) pattern in some Spring state machines and parsers.
 */
public class SwitchFallthrough {

    public String classify(int value) {
        String result;
        switch (value) {
            case 1:
            case 2:
                result = "small";
                break;
            case 3:
                result = "medium";
                // intentional fall-through in some legacy code
            case 4:
            case 5:
                if (result == null) {
                    result = "medium-large";
                }
                break;
            default:
                if (value < 0) {
                    result = "negative";
                } else {
                    result = "large";
                }
        }
        return result;
    }

    // Switch expression (arrow form, already partially supported)
    public String describe(int code) {
        return switch (code) {
            case 0, 1 -> "low";
            case 2 -> "medium";
            default -> "high";
        };
    }
}
