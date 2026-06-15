package com.example;

import java.util.Comparator;

/** Tiny fixture: anonymous Comparator class — skeleton parses but fails mypy. */
public class AnonymousComparator {

    public Comparator<String> byLength() {
        return new Comparator<String>() {
            @Override
            public int compare(String a, String b) {
                return Integer.compare(a.length(), b.length());
            }
        };
    }
}
