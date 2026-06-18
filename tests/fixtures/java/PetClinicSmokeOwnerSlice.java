import java.util.List;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.beans.factory.annotation.Autowired;

enum HttpStatus { CREATED }

@Entity
class Owner {
    @Id
    @GeneratedValue
    private Integer id;

    @Column(length = 30, nullable = false)
    private String firstName;

    @Column(length = 30, nullable = false)
    private String lastName;

    @Column(length = 255, nullable = false)
    private String address;

    @Column(length = 80, nullable = false)
    private String city;

    @Column(length = 20, nullable = false)
    private String telephone;
}

class OwnerRequest {
    public String firstName;
    public String lastName;
    public String address;
    public String city;
    public String telephone;
}

interface OwnerRepository extends JpaRepository<Owner, Integer> {}

@RestController
@RequestMapping("/owners")
public class OwnerController {
    @Autowired
    private OwnerRepository ownerRepository;

    @GetMapping("")
    public List<Owner> findOwners(@RequestParam(required = false) String lastName) {
        return ownerRepository.findAll();
    }

    @GetMapping("/{ownerId}")
    public Owner findOwner(@PathVariable("ownerId") int ownerId) {
        return ownerRepository.findById(ownerId);
    }

    @PostMapping("")
    @ResponseStatus(HttpStatus.CREATED)
    public Owner createOwner(@RequestBody OwnerRequest request) {
        return null;
    }
}
