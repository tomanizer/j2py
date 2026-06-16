package example;

class Order {
}

class OrderRepository {
    Order findById(Long id) {
        return new Order();
    }
}

@RestController
@Entity
public class OrderController {
    @Autowired
    private OrderRepository repo;

    @Transactional
    @GetMapping("/{id}")
    public Order get(Long id) {
        return repo.findById(id);
    }
}
