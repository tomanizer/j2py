package org.springframework.core;

public class Overloads {

    private String name;

    public Overloads() {
        this("default");
    }

    public Overloads(String name) {
        this.name = name;
    }

    public String add(String left, String right) {
        return left + right;
    }

    public int add(int left, int right) {
        return left + right;
    }
}
