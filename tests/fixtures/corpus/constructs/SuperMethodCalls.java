package org.springframework.example;

class BaseTransformer {
    void endClass() {}

    Object getGenerator(Object resource) {
        return resource;
    }

    void setTarget(Object target) {}

    boolean cancel(boolean mayInterrupt) {
        return mayInterrupt;
    }
}

class SuperMethodCalls extends BaseTransformer {
    void finish() {
        super.endClass();
    }

    Object generator(Object resource) {
        return super.getGenerator(resource);
    }

    void configure(Object target) {
        super.setTarget(target);
    }

    boolean cancel(boolean mayInterrupt) {
        return super.cancel(mayInterrupt);
    }
}
