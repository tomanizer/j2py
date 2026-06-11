public class Main {
    private String name;
    private int count;

    public Main(String name, int count) {
        this.name = name;
        this.count = count;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public int getCount() {
        return count;
    }

    public static void main(String[] args) {
        Main sample = new Main("alpha", 2);
        System.out.println(sample.getName());
        sample.setName("beta");
        System.out.println(sample.getName());
        System.out.println(sample.getCount());
    }
}
