package org.example;

public class CharArithmetic {

    private char start = 'a';

    public char nextChar(char c) {
        return (char) (c + 1);
    }

    public int charCode(char c) {
        return c + 0;
    }

    public char toUpper(char c) {
        return (char) (c - 32);
    }

    public int distance(char a, char b) {
        return b - a;
    }

    public char shiftStart(int offset) {
        return (char) (start + offset);
    }
}
