package com.example;

/** Tiny fixture: Java assert triggers rule-layer coverage gap (assert_statement). */
public class AssertProbe {

    public void check(int value) {
        assert value > 0 : "must be positive";
    }
}
