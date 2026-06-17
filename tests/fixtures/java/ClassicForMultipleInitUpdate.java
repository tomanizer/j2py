package com.example;

/** Classic for-loops with multiple initializer and updater expressions. */
public class ClassicForMultipleInitUpdate {

    public boolean meetInMiddle(int len2) {
        for (int i = 1, j = len2 - 1; i <= j; i++, j--) {
            if (i == j) {
                return true;
            }
        }
        return false;
    }

    public int sumPair(int limit) {
        int total = 0;
        for (int left = 0, right = limit; left < right; left++, right--) {
            total += left + right;
        }
        return total;
    }

    public int countWithAssignments(int limit) {
        int i;
        int j;
        int seen = 0;
        for (i = 0, j = limit; i < j; i++, j--) {
            seen += 1;
        }
        return seen;
    }
}
