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
