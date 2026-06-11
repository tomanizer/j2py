package org.springframework.example;

/**
 * Advanced enum with constructor, fields, methods, and interface implementation.
 * Common pattern in Spring for status codes, modes, types with behavior.
 */
public enum AdvancedEnum implements Describable {

    ACTIVE("Active user", 1),
    INACTIVE("Inactive", 0),
    PENDING("Pending verification", 2);

    private final String description;
    private final int priority;

    AdvancedEnum(String description, int priority) {
        this.description = description;
        this.priority = priority;
    }

    public int getPriority() {
        return priority;
    }

    @Override
    public String describe() {
        return name() + " (" + description + ", prio=" + priority + ")";
    }

    public static AdvancedEnum fromPriority(int p) {
        for (AdvancedEnum e : values()) {
            if (e.priority == p) {
                return e;
            }
        }
        throw new IllegalArgumentException("No enum for priority " + p);
    }

    public interface Describable {
        String describe();
    }
}
