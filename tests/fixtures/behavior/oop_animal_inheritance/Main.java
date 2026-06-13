class Animal {
    String sound() { return "..."; }
    String describe() { return "I say " + this.sound(); }
}
class Cat extends Animal {
    String sound() { return "meow"; }
}
class Cow extends Animal {
    String sound() { return "moo"; }
}
public class Main {
    public static void main(String[] args) {
        Animal cat = new Cat();
        Animal cow = new Cow();
        System.out.println(cat.describe());
        System.out.println(cow.describe());
    }
}
