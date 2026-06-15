package org.springframework.example;

/**
 * Comments inside expression lists should not become expression operands.
 */
public class LineCommentInExpression {

    public int[] opcodeValues() {
        return new int[] {
                0, // nop
                1, // aconst_null
                2  // iconst_m1
        };
    }

    public String[] labels() {
        return new String[] {
                "alpha", // first
                "beta"   // second
        };
    }
}
