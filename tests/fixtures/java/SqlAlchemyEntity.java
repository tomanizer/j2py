import jakarta.persistence.CascadeType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;
import jakarta.validation.constraints.NotEmpty;
import java.util.List;

class Person {
}

@Entity
@Table(name = "owners")
class Owner extends Person {
    @Id
    @GeneratedValue
    private Integer id;

    @Column(name = "address", length = 120, nullable = false)
    @NotEmpty
    private String address;

    @OneToMany(cascade = CascadeType.ALL, mappedBy = "owner")
    private List<Pet> pets;

    public String getAddress() { return address; }
    public void setAddress(String address) { this.address = address; }
}

@Entity
class Pet {
    @Id
    private Integer id;

    @ManyToOne
    @JoinColumn(name = "owner_id")
    private Owner owner;

    public Owner getOwner() { return owner; }
}
