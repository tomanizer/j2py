package com.example;

public class PatternMatchSwitch {
    public String describe(Object obj) {
        String result = switch (obj) {
            case Integer i -> "int: " + i;
            case String s when s.isEmpty() -> "empty string";
            case String s -> "string: " + s;
            case null -> "null";
            default -> "other: " + obj;
        };
        return result;
    }
}
