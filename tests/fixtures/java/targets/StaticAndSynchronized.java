package org.springframework.core;

public class StaticAndSynchronized {

    static {
        initialize();
    }

    public void guarded() {
        synchronized (this) {
            run();
        }
    }
}
