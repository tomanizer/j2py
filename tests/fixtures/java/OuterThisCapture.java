package com.example;

public interface Task {
    void run();
}

public class OuterThisCapture {
    private String name;

    public Task createTask() {
        return new Task() {
            @Override
            public void run() {
                System.out.println(OuterThisCapture.this.name);
                OuterThisCapture.this.process();
            }
        };
    }

    private void process() {
        System.out.println(name);
    }

    public class InnerTask {
        public String owner() {
            return OuterThisCapture.this.name;
        }
    }

    public InnerTask createInner() {
        return new InnerTask();
    }
}
