public class ThrowVarargsConstructor {
    public void check(String found, int position, String... expected) {
        throw new UnexpectedTokenException(found, position, expected);
    }
}

class UnexpectedTokenException extends RuntimeException {
    UnexpectedTokenException(String found, int position, String... expected) {
        super(found);
    }
}
