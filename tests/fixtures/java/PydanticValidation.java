class CreateOwnerForm {
    @NotNull
    @Size(min = 1, max = 30)
    private String firstName;

    @Min(0)
    @Max(150)
    private int age;

    @Pattern(regexp = "[A-Z]+")
    @NotEmpty
    private String code;

    @Digits(integer = 3, fraction = 2)
    private int price;
}
