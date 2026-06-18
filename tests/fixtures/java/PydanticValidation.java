class CreateOwnerForm {
    @NotNull
    @Size(min = 1, max = 30)
    private String firstName;

    @Min(0)
    @Max(150)
    private int age;

    @Max(10)
    private int retries = 3;

    @Min(10L)
    @Max(0x20)
    private long stock;

    @Max(0b1010)
    private int binaryLimit;

    @Pattern(regexp = "[A-Z]+")
    @NotEmpty
    private String code;

    @Size(max = 60)
    private String nickname;

    @Pattern(regexp = "[a-z]+")
    private String slug;

    @Digits(integer = 3, fraction = 2)
    private int price;
}
