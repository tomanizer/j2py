abstract class Employee {
    private final String name;
    Employee(String name) { this.name = name; }
    abstract int monthlyPay();
    String slip() { return this.name + ": " + this.monthlyPay(); }
}
class Salaried extends Employee {
    private final int annual;
    Salaried(String name, int annual) { super(name); this.annual = annual; }
    int monthlyPay() { return this.annual % 12 + 2000; }
}
public class Main {
    public static void main(String[] args) {
        Employee e = new Salaried("ada", 24000);
        System.out.println(e.slip());
    }
}
