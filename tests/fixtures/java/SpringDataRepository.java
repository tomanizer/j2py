package example;

import java.util.Collection;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

class Owner {
}

interface OwnerRepository extends JpaRepository<Owner, Integer> {
    @Query("SELECT o FROM Owner o WHERE o.lastName = :lastName")
    Collection<Owner> findByLastName(@Param("lastName") String lastName);

    Collection<Owner> findByCity(String city);
}
