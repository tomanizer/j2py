package com.example;

/** Tiny fixture: Java assert translates in the deterministic rule layer. */
public class AssertProbe {

    public void check(int value) {
        assert value > 0 : "must be positive";
    }
}
