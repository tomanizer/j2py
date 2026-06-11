package org.springframework.example;

import java.util.Comparator;
import java.util.concurrent.Callable;

/**
 * Minimal examples for anonymous classes and local/inner classes.
 * Very common in Spring for comparators, listeners, callbacks, Runnables, etc.
 */
public class AnonymousAndInner {

    // Anonymous class in expression position (very common)
    public Comparator<String> lengthComparator() {
        return new Comparator<String>() {
            @Override
            public int compare(String a, String b) {
                return Integer.compare(a.length(), b.length());
            }
        };
    }

    // Anonymous implementing interface with state
    public Callable<String> makeTask(final String prefix) {
        return new Callable<String>() {
            private int counter = 0;

            @Override
            public String call() {
                counter++;
                return prefix + "-" + counter;
            }
        };
    }

    // Local class inside method
    public void processWithLocal(final int threshold) {
        class ThresholdFilter {
            boolean accepts(int value) {
                return value > threshold;
            }
        }

        ThresholdFilter filter = new ThresholdFilter();
        // usage would be here in real code
        if (filter.accepts(42)) {
            System.out.println("accepted");
        }
    }

    // Non-static inner class (captures outer)
    public class InnerHandler {
        public String handle(String input) {
            // can access outer instance implicitly
            return "inner:" + input;
        }
    }

    public InnerHandler createHandler() {
        return new InnerHandler();
    }
}
