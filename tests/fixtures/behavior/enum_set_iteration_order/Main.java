import java.util.EnumSet;

public class Main {
    enum Day { MON, TUE, WED, THU, FRI }

    public static void main(String[] args) {
        // Construction order is deliberately not ordinal order; Java's EnumSet
        // iterates and renders in ordinal (declaration) order, and a plain
        // Python set would lose both. toString prints bare names in brackets.
        EnumSet<Day> set = EnumSet.of(Day.FRI, Day.MON, Day.WED);
        System.out.println(set);
        EnumSet<Day> single = EnumSet.of(Day.THU);
        System.out.println(single);
        EnumSet<Day> spanned = EnumSet.range(Day.MON, Day.WED);
        System.out.println(spanned);
        int count = 0;
        for (Day day : set) {
            count++;
        }
        System.out.println(count);
    }
}
