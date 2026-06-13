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

    public int negativeIntShift() {
        int value = -1;
        return value >>> 1;
    }

    public long unsignedLongShift(long value) {
        return value >>> 2;
    }

    public int unsignedAssign(int value) {
        value >>>= 1;
        return value;
    }

    public int unknownWidth(Source source) {
        return source.value() >>> 1;
    }

    interface Source {
        int value();
    }
}
