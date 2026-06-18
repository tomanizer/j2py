import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;

class OwnerController {
    @PostMapping("/owners")
    public OwnerRequest processCreationForm(@Valid @RequestBody OwnerRequest form) {
        return form;
    }
}

class OwnerRequest {
    @NotNull
    @Size(min = 1, max = 30)
    private String firstName;
    private String lastName;

    public OwnerRequest() {}
    public String getFirstName() { return firstName; }
    public void setFirstName(String firstName) { this.firstName = firstName; }
    public String getLastName() { return lastName; }
    public void setLastName(String lastName) { this.lastName = lastName; }
}
