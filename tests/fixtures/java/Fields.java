package com.example;

public class Fields {

    private static int total = 0;
    private String name = "anonymous";
    private int count;
    private boolean enabled;

    public Fields(int count) {
        this.count = count;
    }

    public String getName() {
        return name;
    }
}
