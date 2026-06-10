package com.example;

import java.util.List;
import java.util.ArrayList;

public class HelloWorld {

    private String name;
    private final int count;

    public HelloWorld(String name, int count) {
        this.name = name;
        this.count = count;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public List<String> greetAll(List<String> people) {
        List<String> greetings = new ArrayList<>();
        for (String person : people) {
            greetings.add("Hello, " + person + "!");
        }
        return greetings;
    }

    public static void main(String[] args) {
        HelloWorld hw = new HelloWorld("World", 1);
        System.out.println(hw.getName());
    }
}
