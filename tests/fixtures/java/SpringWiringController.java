@interface RestController {}
@interface RequestMapping {
    String value() default "";
}
@interface GetMapping {
    String value() default "";
}
@interface PostMapping {
    String value() default "";
}
@interface PutMapping {
    String value() default "";
}
@interface DeleteMapping {
    String value() default "";
}
@interface ResponseStatus {
    int value();
}
@interface PathVariable {
    String value() default "";
}
@interface RequestParam {
    String value() default "";
    boolean required() default true;
}
@interface RequestBody {}
@interface Autowired {}
@interface Qualifier {
    String value();
}

interface OwnerService {}
class Owner {}
class OwnerForm {}

@RestController
@RequestMapping("/owners")
public class SpringWiringController {
    @Autowired
    @Qualifier("ownerService")
    private OwnerService ownerService;

    @GetMapping("/{ownerId}")
    public Owner findOwner(
        @PathVariable("ownerId") int ownerId,
        @RequestParam(value = "lastName", required = false) String lastName
    ) {
        return null;
    }

    @PostMapping("")
    @ResponseStatus(201)
    public Owner createOwner(@RequestBody OwnerForm form) {
        return null;
    }

    @PutMapping("/{ownerId}")
    public Owner updateOwner(@PathVariable("ownerId") int ownerId, @RequestBody OwnerForm form) {
        return null;
    }

    @DeleteMapping("/{ownerId}")
    public void deleteOwner(@PathVariable("ownerId") int ownerId) {
    }
}
