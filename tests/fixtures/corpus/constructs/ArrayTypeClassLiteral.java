package org.springframework.example;

/**
 * Minimal example for Java array type class literals.
 */
public class ArrayTypeClassLiteral {

    public Class<?> primitiveArrayType() {
        return boolean[].class;
    }

    public Class<?> referenceArrayType() {
        return String[].class;
    }

    public boolean isPrimitiveBooleanArray(Class<?> candidate) {
        return candidate == boolean[].class;
    }

    public boolean isPrimitiveIntArray(Class<?> candidate) {
        return candidate == int[].class;
    }

    public boolean isQualifiedStringArray(Class<?> candidate) {
        return candidate == java.lang.String[].class;
    }

    public boolean isPrimitiveIntMatrix(Class<?> candidate) {
        return candidate == int[][].class;
    }

    public boolean samePrimitiveArrayLiteral() {
        return boolean[].class == boolean[].class;
    }
}
