package com.google.common.math;

/**
 * Minimal Guava-style arithmetic fixture for the Phase-1 equivalence exit criterion.
 *
 * <p>The shape mirrors the precedence-sensitive bug class seen in Guava: a parenthesized
 * additive expression used as a multiplicative operand must not translate from
 * {@code (a + b) * c} to {@code a + b * c}.
 */
public final class GuavaPrecedenceMath {

    private GuavaPrecedenceMath() {
    }

    public static int expandedCapacity(int oldCapacity) {
        return (oldCapacity + 1) * 2;
    }

    public static int scaledSum(int left, int right, int scale) {
        return (left + right) * scale;
    }
}
