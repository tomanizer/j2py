package org.springframework.asm;

public class CompoundAssignment {

    public int update(int value, int mask, int flag) {
        value &= mask;
        value |= flag;
        return value;
    }
}
