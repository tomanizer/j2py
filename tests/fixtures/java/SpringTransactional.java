package example;

@interface Transactional {
    boolean readOnly() default false;
    Class<?>[] rollbackFor() default {};
}

class Owner {
}

class AuditException {
}

class BaseService {
    public String describe() {
        return "base";
    }
}

@Transactional(readOnly = true)
public class OwnerService extends BaseService {
    public Owner findOwner(Long id) {
        return new Owner();
    }

    void packagePrivateHelper() {
    }

    @Override
    public String describe() {
        return "owner";
    }

    @Transactional(rollbackFor = AuditException.class)
    public void saveOwner(Owner owner) {
        packagePrivateHelper();
    }
}
