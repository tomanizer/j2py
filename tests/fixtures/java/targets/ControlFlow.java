package org.springframework.core;

public class ControlFlow {

    public int classify(int value, int limit) {
        int total = 0;
        if (value > 10) {
            total = value;
        }
        else if (value == 10) {
            total = 1;
        }
        else {
            total = -1;
        }

        for (int i = 0; i < limit; i++) {
            total += i;
        }

        while (total < 100) {
            total++;
        }

        do {
            total--;
        }
        while (total > 100);

        return total;
    }
}
