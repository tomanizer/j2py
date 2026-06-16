package example;

@interface Service {}
@interface RestController {}
@interface Autowired {}
@interface Entity {}

interface OrderRepository {}

@Service
@RestController
public class OrderController {
    @Autowired
    private OrderRepository repo;
}

@Entity
public class User {
    private Long id;
}
