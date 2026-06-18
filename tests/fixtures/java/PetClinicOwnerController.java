import java.util.List;

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
@interface ResponseStatus {
    HttpStatus value();
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

enum HttpStatus { CREATED }

interface OwnerRepository {}
class Owner {}
class OwnerRequest {}

@RestController
@RequestMapping("/owners")
public class OwnerController {
    @Autowired
    private OwnerRepository ownerRepository;

    @GetMapping("")
    public List<Owner> findOwners(@RequestParam(required = false) String lastName) {
        return null;
    }

    @GetMapping("/{ownerId}")
    public Owner findOwner(@PathVariable("ownerId") int ownerId) {
        return null;
    }

    @PostMapping("")
    @ResponseStatus(HttpStatus.CREATED)
    public Owner createOwner(@RequestBody OwnerRequest request) {
        return null;
    }
}
