package org.springframework.asm;

public class BitwiseOperators {

    public int flags(int left, int right) {
        return (left & right) | (left ^ right);
    }

    public int shifts(int value) {
        return (value << 2) >> 1;
    }

    public int unsignedShift(int value) {
        return value >>> 1;
    }
}
