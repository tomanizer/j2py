"""Generate the j2py behavior-equivalence corpus.

Every case is a self-contained Java program whose translated Python (RULE LAYER ONLY,
no LLM) must produce byte-identical stdout/stderr/return-code. Cases are deliberately
kept inside the deterministic rule layer's *runtime-correct* envelope:

  - Top-level classes only; `main` instantiates and calls INSTANCE methods.
  - Output is ints and strings only (never raw boolean/null/float/char -> printing
    differs between Java and Python).
  - Arithmetic uses + - * % and bitwise & | ^ only. No `/` (rule layer punts mixed
    int division) and no parenthesised grouping (kept out to dodge precedence edges).
  - Always braces; for-loops counted; string concat only inside println.
  - Strings limited to length/upper/lower/replace/trim/isEmpty/contains/startsWith/
    equals/split. Lists via simple import: add/get/size/contains/Collections.sort.

This envelope is the contract the corpus guarantees. As the rule layer grows, add
cases here and regenerate.
"""
import shutil
from pathlib import Path

CASES: dict[str, str] = {}


def case(name: str, src: str) -> None:
    CASES[name] = src.lstrip()


# ----------------------------------------------------------------- algorithms
case("algo_factorial_iter", """
public class Main {
    int factorial(int n) {
        int result = 1;
        for (int i = 2; i <= n; i++) { result = result * i; }
        return result;
    }
    public static void main(String[] args) {
        Main m = new Main();
        System.out.println(m.factorial(6));
    }
}
""")
case("algo_factorial_rec", """
public class Main {
    int factorial(int n) {
        if (n <= 1) { return 1; }
        return n * this.factorial(n - 1);
    }
    public static void main(String[] args) {
        Main m = new Main();
        System.out.println(m.factorial(7));
    }
}
""")
case("algo_fibonacci_iter", """
public class Main {
    public static void main(String[] args) {
        int a = 0, b = 1;
        for (int i = 0; i < 10; i++) {
            System.out.println(a);
            int next = a + b;
            a = b;
            b = next;
        }
    }
}
""")
case("algo_fibonacci_rec", """
public class Main {
    int fib(int n) {
        if (n < 2) { return n; }
        return this.fib(n - 1) + this.fib(n - 2);
    }
    public static void main(String[] args) {
        Main m = new Main();
        for (int i = 0; i < 10; i++) { System.out.println(m.fib(i)); }
    }
}
""")
case("algo_gcd", """
public class Main {
    int gcd(int a, int b) {
        while (b != 0) {
            int t = b;
            b = a % b;
            a = t;
        }
        return a;
    }
    public static void main(String[] args) {
        Main m = new Main();
        System.out.println(m.gcd(48, 36));
        System.out.println(m.gcd(17, 5));
    }
}
""")
case("algo_power", """
public class Main {
    int power(int base, int exp) {
        int result = 1;
        for (int i = 0; i < exp; i++) { result = result * base; }
        return result;
    }
    public static void main(String[] args) {
        Main m = new Main();
        System.out.println(m.power(2, 10));
        System.out.println(m.power(3, 4));
    }
}
""")
case("algo_sum_squares", """
public class Main {
    int sumSquares(int n) {
        int total = 0;
        for (int i = 1; i <= n; i++) { total += i * i; }
        return total;
    }
    public static void main(String[] args) {
        Main m = new Main();
        System.out.println(m.sumSquares(5));
        System.out.println(m.sumSquares(10));
    }
}
""")
case("algo_collatz", """
public class Main {
    int steps(int n) {
        int count = 0;
        while (n != 1) {
            if (n % 2 == 0) { n = n - n / 2; } else { n = 3 * n + 1; }
            count++;
        }
        return count;
    }
    public static void main(String[] args) {
        Main m = new Main();
        System.out.println(m.steps(6));
    }
}
""")
case("algo_is_prime", """
public class Main {
    String classify(int n) {
        if (n < 2) { return "no"; }
        for (int d = 2; d < n; d++) {
            if (n % d == 0) { return "no"; }
        }
        return "yes";
    }
    public static void main(String[] args) {
        Main m = new Main();
        int[] xs = {1, 2, 9, 13, 15, 17};
        for (int x : xs) { System.out.println(m.classify(x)); }
    }
}
""")
case("algo_count_primes", """
public class Main {
    boolean isPrime(int n) {
        if (n < 2) { return false; }
        for (int d = 2; d < n; d++) {
            if (n % d == 0) { return false; }
        }
        return true;
    }
    public static void main(String[] args) {
        Main m = new Main();
        int count = 0;
        for (int i = 0; i < 30; i++) {
            if (m.isPrime(i)) { count++; }
        }
        System.out.println(count);
    }
}
""")
case("algo_triangular", """
public class Main {
    int triangular(int n) {
        int total = 0;
        for (int i = 1; i <= n; i++) { total += i; }
        return total;
    }
    public static void main(String[] args) {
        Main m = new Main();
        for (int n = 1; n <= 5; n++) { System.out.println(m.triangular(n)); }
    }
}
""")
case("algo_fizzbuzz", """
public class Main {
    public static void main(String[] args) {
        for (int i = 1; i <= 20; i++) {
            if (i % 15 == 0) { System.out.println("FizzBuzz"); }
            else if (i % 3 == 0) { System.out.println("Fizz"); }
            else if (i % 5 == 0) { System.out.println("Buzz"); }
            else { System.out.println(i); }
        }
    }
}
""")
case("algo_max_of_three", """
public class Main {
    int maxOf(int a, int b, int c) {
        return Math.max(a, Math.max(b, c));
    }
    public static void main(String[] args) {
        Main m = new Main();
        System.out.println(m.maxOf(3, 9, 5));
        System.out.println(m.maxOf(8, 2, 4));
    }
}
""")
case("algo_abs_diff", """
public class Main {
    int absDiff(int a, int b) { return Math.abs(a - b); }
    public static void main(String[] args) {
        Main m = new Main();
        System.out.println(m.absDiff(3, 10));
        System.out.println(m.absDiff(10, 3));
    }
}
""")
case("algo_count_down_up", """
public class Main {
    public static void main(String[] args) {
        for (int i = 5; i > 0; i--) { System.out.println(i); }
        for (int i = 1; i <= 5; i++) { System.out.println(i); }
    }
}
""")

# ----------------------------------------------------------------- strings
case("str_upper_lower", """
public class Main {
    public static void main(String[] args) {
        String s = "MixedCase";
        System.out.println(s.toUpperCase());
        System.out.println(s.toLowerCase());
        System.out.println(s.length());
    }
}
""")
case("str_replace_chain", """
public class Main {
    String censor(String s) {
        return s.replace("a", "*").replace("e", "*").replace("i", "*");
    }
    public static void main(String[] args) {
        Main m = new Main();
        System.out.println(m.censor("aerial gaze"));
    }
}
""")
case("str_word_count", """
public class Main {
    int words(String text) {
        String[] parts = text.split(" ");
        return parts.length;
    }
    public static void main(String[] args) {
        Main m = new Main();
        System.out.println(m.words("the quick brown fox"));
    }
}
""")
case("str_split_print", """
public class Main {
    public static void main(String[] args) {
        String csv = "alpha,beta,gamma";
        String[] parts = csv.split(",");
        for (String p : parts) { System.out.println(p); }
        System.out.println(parts.length);
    }
}
""")
case("str_contains_starts", """
public class Main {
    public static void main(String[] args) {
        String s = "hello world";
        System.out.println(s.contains("world") ? "has" : "missing");
        System.out.println(s.startsWith("hello") ? "starts" : "no");
        System.out.println(s.equals("hello world") ? "eq" : "ne");
    }
}
""")
case("str_concat_greeting", """
public class Main {
    String greet(String name, int times) {
        return "hi " + name + " x" + times;
    }
    public static void main(String[] args) {
        Main m = new Main();
        System.out.println(m.greet("bob", 3));
    }
}
""")
case("str_trim_empty", """
public class Main {
    String tidy(String s) {
        String t = s.trim();
        return t.isEmpty() ? "blank" : t;
    }
    public static void main(String[] args) {
        Main m = new Main();
        System.out.println(m.tidy("   spaced   "));
        System.out.println(m.tidy("    "));
    }
}
""")
case("str_longest_word", """
public class Main {
    String longest(String text) {
        String[] parts = text.split(" ");
        String best = "";
        for (String p : parts) {
            if (p.length() > best.length()) { best = p; }
        }
        return best;
    }
    public static void main(String[] args) {
        Main m = new Main();
        System.out.println(m.longest("a bb cccc dd"));
    }
}
""")
case("str_repeat_lines", """
public class Main {
    void repeat(String s, int n) {
        for (int i = 0; i < n; i++) { System.out.println(s); }
    }
    public static void main(String[] args) {
        Main m = new Main();
        m.repeat("echo", 3);
    }
}
""")

# ----------------------------------------------------------------- arrays
case("arr_sum", """
public class Main {
    int total(int[] a) {
        int acc = 0;
        for (int i = 0; i < a.length; i++) { acc += a[i]; }
        return acc;
    }
    public static void main(String[] args) {
        Main m = new Main();
        int[] a = {4, 8, 15, 16, 23, 42};
        System.out.println(m.total(a));
    }
}
""")
case("arr_max_min", """
public class Main {
    public static void main(String[] args) {
        int[] a = {7, 2, 9, 4, 1};
        int max = a[0], min = a[0];
        for (int x : a) {
            if (x > max) { max = x; }
            if (x < min) { min = x; }
        }
        System.out.println(max);
        System.out.println(min);
    }
}
""")
case("arr_count_evens", """
public class Main {
    int countEvens(int[] a) {
        int count = 0;
        for (int x : a) {
            if (x % 2 == 0) { count++; }
        }
        return count;
    }
    public static void main(String[] args) {
        Main m = new Main();
        int[] a = {1, 2, 3, 4, 5, 6};
        System.out.println(m.countEvens(a));
    }
}
""")
case("arr_reverse_print", """
public class Main {
    public static void main(String[] args) {
        int[] a = {10, 20, 30, 40};
        int i = a.length - 1;
        while (i >= 0) {
            System.out.println(a[i]);
            i--;
        }
    }
}
""")
case("arr_linear_search", """
public class Main {
    int find(int[] a, int target) {
        for (int i = 0; i < a.length; i++) {
            if (a[i] == target) { return i; }
        }
        return -1;
    }
    public static void main(String[] args) {
        Main m = new Main();
        int[] a = {5, 10, 15, 20};
        System.out.println(m.find(a, 15));
        System.out.println(m.find(a, 99));
    }
}
""")
case("arr_2d_sum", """
public class Main {
    public static void main(String[] args) {
        int[][] grid = {{1, 2, 3}, {4, 5, 6}};
        int total = 0;
        for (int i = 0; i < grid.length; i++) {
            for (int j = 0; j < grid[i].length; j++) { total += grid[i][j]; }
        }
        System.out.println(total);
    }
}
""")
case("arr_bubble_sort", """
public class Main {
    public static void main(String[] args) {
        int[] a = {5, 2, 8, 1, 9, 3};
        int n = a.length;
        for (int i = 0; i < n; i++) {
            for (int j = 0; j < n - 1; j++) {
                if (a[j] > a[j + 1]) {
                    int t = a[j];
                    a[j] = a[j + 1];
                    a[j + 1] = t;
                }
            }
        }
        for (int x : a) { System.out.println(x); }
    }
}
""")
case("arr_string_join_print", """
public class Main {
    public static void main(String[] args) {
        String[] names = {"ann", "ben", "cy"};
        for (int i = 0; i < names.length; i++) {
            System.out.println("name " + i + " = " + names[i]);
        }
    }
}
""")

# ----------------------------------------------------------------- collections
case("coll_list_sum", """
import java.util.ArrayList;
import java.util.List;
public class Main {
    public static void main(String[] args) {
        List<Integer> xs = new ArrayList<>();
        for (int i = 1; i <= 5; i++) { xs.add(i * i); }
        int total = 0;
        for (int x : xs) { total += x; }
        System.out.println(total);
        System.out.println(xs.size());
    }
}
""")
case("coll_list_max", """
import java.util.ArrayList;
import java.util.List;
public class Main {
    int maxOf(List<Integer> xs) {
        int best = xs.get(0);
        for (int x : xs) {
            if (x > best) { best = x; }
        }
        return best;
    }
    public static void main(String[] args) {
        List<Integer> xs = new ArrayList<>();
        xs.add(3); xs.add(11); xs.add(7);
        Main m = new Main();
        System.out.println(m.maxOf(xs));
    }
}
""")
case("coll_list_sort", """
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
public class Main {
    public static void main(String[] args) {
        List<Integer> xs = new ArrayList<>();
        xs.add(5); xs.add(1); xs.add(4); xs.add(2); xs.add(3);
        Collections.sort(xs);
        for (int x : xs) { System.out.println(x); }
    }
}
""")
case("coll_list_contains", """
import java.util.ArrayList;
import java.util.List;
public class Main {
    public static void main(String[] args) {
        List<String> words = new ArrayList<>();
        words.add("cat"); words.add("dog");
        System.out.println(words.contains("dog") ? "found" : "absent");
        System.out.println(words.contains("fish") ? "found" : "absent");
    }
}
""")
case("coll_list_filter", """
import java.util.ArrayList;
import java.util.List;
public class Main {
    List<Integer> evens(List<Integer> xs) {
        List<Integer> out = new ArrayList<>();
        for (int x : xs) {
            if (x % 2 == 0) { out.add(x); }
        }
        return out;
    }
    public static void main(String[] args) {
        List<Integer> xs = new ArrayList<>();
        for (int i = 1; i <= 10; i++) { xs.add(i); }
        Main m = new Main();
        List<Integer> result = m.evens(xs);
        for (int x : result) { System.out.println(x); }
    }
}
""")

# ----------------------------------------------------------------- oop
case("oop_rectangle", """
public class Main {
    private final int width;
    private final int height;
    Main(int width, int height) { this.width = width; this.height = height; }
    int area() { return this.width * this.height; }
    int perimeter() { return 2 * this.width + 2 * this.height; }
    public static void main(String[] args) {
        Main r = new Main(4, 6);
        System.out.println(r.area());
        System.out.println(r.perimeter());
    }
}
""")
case("oop_bank_account", """
public class Main {
    private int balance;
    Main() { this.balance = 0; }
    void deposit(int amount) { this.balance += amount; }
    void withdraw(int amount) { this.balance -= amount; }
    int getBalance() { return this.balance; }
    public static void main(String[] args) {
        Main acct = new Main();
        acct.deposit(200);
        acct.withdraw(75);
        acct.deposit(50);
        System.out.println(acct.getBalance());
    }
}
""")
case("oop_counter", """
public class Main {
    private int value = 0;
    void increment() { this.value++; }
    void reset() { this.value = 0; }
    int get() { return this.value; }
    public static void main(String[] args) {
        Main c = new Main();
        for (int i = 0; i < 7; i++) { c.increment(); }
        System.out.println(c.get());
        c.reset();
        System.out.println(c.get());
    }
}
""")
case("oop_taxi_fare", """
public class Main {
    private final int baseFare;
    private final int perMile;
    Main(int baseFare, int perMile) { this.baseFare = baseFare; this.perMile = perMile; }
    int fare(int miles) { return this.baseFare + this.perMile * miles; }
    public static void main(String[] args) {
        Main cab = new Main(3, 2);
        System.out.println(cab.fare(0));
        System.out.println(cab.fare(10));
    }
}
""")
case("oop_calculator", """
public class Main {
    int plus(int a, int b) { return a + b; }
    int minus(int a, int b) { return a - b; }
    int times(int a, int b) { return a * b; }
    public static void main(String[] args) {
        Main c = new Main();
        System.out.println(c.plus(3, 4));
        System.out.println(c.minus(10, 6));
        System.out.println(c.times(5, 5));
    }
}
""")
case("oop_animal_inheritance", """
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
""")
case("oop_shape_interface", """
interface Shape { int area(); }
class Square implements Shape {
    private final int side;
    Square(int side) { this.side = side; }
    public int area() { return this.side * this.side; }
}
class Rect implements Shape {
    private final int w;
    private final int h;
    Rect(int w, int h) { this.w = w; this.h = h; }
    public int area() { return this.w * this.h; }
}
public class Main {
    public static void main(String[] args) {
        Shape a = new Square(5);
        Shape b = new Rect(3, 4);
        System.out.println(a.area());
        System.out.println(b.area());
    }
}
""")
case("oop_shape_polymorphism", """
import java.util.ArrayList;
import java.util.List;
interface Shape { int area(); }
class Square implements Shape {
    private final int side;
    Square(int side) { this.side = side; }
    public int area() { return this.side * this.side; }
}
class Rect implements Shape {
    private final int w;
    private final int h;
    Rect(int w, int h) { this.w = w; this.h = h; }
    public int area() { return this.w * this.h; }
}
public class Main {
    public static void main(String[] args) {
        List<Shape> shapes = new ArrayList<>();
        shapes.add(new Square(2));
        shapes.add(new Rect(3, 4));
        shapes.add(new Square(5));
        int total = 0;
        for (Shape s : shapes) { total += s.area(); }
        System.out.println(total);
    }
}
""")
case("oop_abstract_base", """
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
""")
case("oop_super_call", """
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
""")
case("oop_point", """
public class Main {
    private final int x;
    private final int y;
    Main(int x, int y) { this.x = x; this.y = y; }
    int manhattan(Main other) { return Math.abs(this.x - other.x) + Math.abs(this.y - other.y); }
    String show() { return "(" + this.x + "," + this.y + ")"; }
    public static void main(String[] args) {
        Main a = new Main(1, 2);
        Main b = new Main(4, 6);
        System.out.println(a.show());
        System.out.println(a.manhattan(b));
    }
}
""")
case("oop_stack_list", """
import java.util.ArrayList;
import java.util.List;
public class Main {
    private final List<Integer> items = new ArrayList<>();
    void push(int x) { this.items.add(x); }
    int depth() { return this.items.size(); }
    int peek() {
        int last = this.items.size() - 1;
        return this.items.get(last);
    }
    public static void main(String[] args) {
        Main s = new Main();
        s.push(10); s.push(20); s.push(30);
        System.out.println(s.depth());
        System.out.println(s.peek());
    }
}
""")
case("oop_toggle_state", """
public class Main {
    private boolean on = false;
    void flip() { this.on = !this.on; }
    String state() { return this.on ? "ON" : "OFF"; }
    public static void main(String[] args) {
        Main t = new Main();
        System.out.println(t.state());
        t.flip();
        System.out.println(t.state());
        t.flip();
        System.out.println(t.state());
    }
}
""")

# ----------------------------------------------------------------- control flow
case("cf_grade", """
public class Main {
    String grade(int score) {
        if (score >= 90) { return "A"; }
        else if (score >= 80) { return "B"; }
        else if (score >= 70) { return "C"; }
        else { return "F"; }
    }
    public static void main(String[] args) {
        Main m = new Main();
        int[] scores = {95, 83, 71, 50};
        for (int s : scores) { System.out.println(m.grade(s)); }
    }
}
""")
case("cf_sign", """
public class Main {
    String sign(int n) {
        if (n > 0) { return "positive"; }
        else if (n < 0) { return "negative"; }
        else { return "zero"; }
    }
    public static void main(String[] args) {
        Main m = new Main();
        int[] xs = {5, -3, 0};
        for (int x : xs) { System.out.println(m.sign(x)); }
    }
}
""")
case("cf_leap_year", """
public class Main {
    String leap(int y) {
        if (y % 4 == 0 && y % 100 != 0 || y % 400 == 0) { return "leap"; }
        return "common";
    }
    public static void main(String[] args) {
        Main m = new Main();
        int[] years = {2000, 1900, 2024, 2023};
        for (int y : years) { System.out.println(m.leap(y)); }
    }
}
""")
case("cf_switch_weekday", """
public class Main {
    String name(int d) {
        switch (d) {
            case 1: return "Mon";
            case 2: return "Tue";
            case 3: return "Wed";
            default: return "Other";
        }
    }
    public static void main(String[] args) {
        Main m = new Main();
        for (int i = 1; i <= 4; i++) { System.out.println(m.name(i)); }
    }
}
""")
case("cf_break_continue", """
public class Main {
    public static void main(String[] args) {
        int total = 0;
        for (int i = 1; i < 100; i++) {
            if (i % 2 == 0) { continue; }
            if (i > 9) { break; }
            total += i;
        }
        System.out.println(total);
    }
}
""")
case("cf_nested_loop_pattern", """
public class Main {
    public static void main(String[] args) {
        for (int i = 1; i <= 4; i++) {
            String row = "";
            for (int j = 0; j < i; j++) { System.out.println("row " + i + " star " + j); }
        }
    }
}
""")
case("cf_do_while", """
public class Main {
    public static void main(String[] args) {
        int n = 1, product = 1;
        do {
            product = product * n;
            n++;
        } while (n <= 5);
        System.out.println(product);
    }
}
""")
case("cf_while_accumulate", """
public class Main {
    public static void main(String[] args) {
        int i = 1, sum = 0;
        while (i <= 10) {
            sum += i;
            i++;
        }
        System.out.println(sum);
    }
}
""")
case("cf_ternary_classify", """
public class Main {
    public static void main(String[] args) {
        for (int i = 0; i < 5; i++) {
            String label = i % 2 == 0 ? "even" : "odd";
            System.out.println("n " + i + " " + label);
        }
    }
}
""")
case("cf_guard_clause", """
public class Main {
    String check(int age) {
        if (age < 0) { return "invalid"; }
        if (age < 18) { return "minor"; }
        if (age < 65) { return "adult"; }
        return "senior";
    }
    public static void main(String[] args) {
        Main m = new Main();
        int[] ages = {-1, 10, 30, 70};
        for (int a : ages) { System.out.println(m.check(a)); }
    }
}
""")

# ----------------------------------------------------------------- numeric / bitwise
case("num_bitwise", """
public class Main {
    public static void main(String[] args) {
        int a = 12, b = 10;
        System.out.println(a & b);
        System.out.println(a | b);
        System.out.println(a ^ b);
    }
}
""")
case("num_modulo_clock", """
public class Main {
    int addHours(int start, int delta) {
        int raw = start + delta;
        return raw % 12;
    }
    public static void main(String[] args) {
        Main m = new Main();
        System.out.println(m.addHours(10, 5));
        System.out.println(m.addHours(3, 24));
    }
}
""")
case("num_parse_and_add", """
public class Main {
    public static void main(String[] args) {
        String[] tokens = {"10", "20", "30"};
        int total = 0;
        for (String t : tokens) { total += Integer.parseInt(t); }
        System.out.println(total);
    }
}
""")
case("num_running_max", """
public class Main {
    public static void main(String[] args) {
        int[] xs = {3, 1, 4, 1, 5, 9, 2, 6};
        int best = xs[0];
        for (int x : xs) { best = Math.max(best, x); }
        System.out.println(best);
    }
}
""")
case("num_sum_multiples", """
public class Main {
    int sumMultiples(int limit) {
        int total = 0;
        for (int i = 0; i < limit; i++) {
            if (i % 3 == 0 || i % 5 == 0) { total += i; }
        }
        return total;
    }
    public static void main(String[] args) {
        Main m = new Main();
        System.out.println(m.sumMultiples(20));
    }
}
""")

# ----------------------------------------------------------------- exceptions
case("exc_catch_message", """
public class Main {
    int safeDivideMod(int a, int b) {
        if (b == 0) { throw new IllegalArgumentException("zero"); }
        return a % b;
    }
    public static void main(String[] args) {
        Main m = new Main();
        try {
            System.out.println(m.safeDivideMod(17, 5));
            System.out.println(m.safeDivideMod(10, 0));
        } catch (IllegalArgumentException e) {
            System.out.println("caught");
        }
    }
}
""")
case("exc_array_bounds", """
public class Main {
    public static void main(String[] args) {
        int[] a = {1, 2, 3};
        try {
            int x = a[10];
            System.out.println(x);
        } catch (ArrayIndexOutOfBoundsException e) {
            System.out.println("out of bounds");
        }
        System.out.println("done");
    }
}
""")
case("exc_finally", """
public class Main {
    public static void main(String[] args) {
        try {
            System.out.println("try");
            throw new RuntimeException("boom");
        } catch (RuntimeException e) {
            System.out.println("catch");
        } finally {
            System.out.println("finally");
        }
    }
}
""")


#: Default output: the committed behavior fixtures directory.
DEFAULT_OUT = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "behavior"


def main() -> None:
    import sys

    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    out.mkdir(parents=True, exist_ok=True)
    # Only (re)write the directories this generator owns; hand-written fixtures and
    # other cases in the same directory are left untouched.
    for name, src in CASES.items():
        d = out / name
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
        (d / "Main.java").write_text(src, encoding="utf-8")
    print(f"generated {len(CASES)} cases into {out}")


if __name__ == "__main__":
    main()
