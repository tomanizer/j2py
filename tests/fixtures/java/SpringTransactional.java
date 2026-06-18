package example;

@interface Transactional {
    boolean readOnly() default false;
    Class<?>[] rollbackFor() default {};
}

class Owner {
}

class AuditException {
}

@Transactional(readOnly = true)
public class OwnerService {
    public Owner findOwner(Long id) {
        return new Owner();
    }

    void packagePrivateHelper() {
    }

    @Transactional(rollbackFor = AuditException.class)
    public void saveOwner(Owner owner) {
        packagePrivateHelper();
    }
}
