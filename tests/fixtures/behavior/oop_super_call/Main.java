class Base {
    String tag() { return "base"; }
}
class Derived extends Base {
    String tag() { return super.tag() + "/derived"; }
}
public class Main {
    public static void main(String[] args) {
        Derived d = new Derived();
        System.out.println(d.tag());
    }
}
