package com.example.shop.web;

import com.example.shop.domain.Order;
import com.example.shop.service.OrderService;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Web layer for orders. Demonstrates @RestController class mapping plus
 * per-method HTTP verb mappings lowering onto a FastAPI APIRouter.
 */
@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public Order get(@PathVariable Long id) {
        return service.findById(id);
    }

    @PostMapping
    public Order create(@RequestBody Order order) {
        return service.save(order);
    }

    @DeleteMapping("/{id}")
    public void delete(@PathVariable Long id) {
        service.deleteById(id);
    }
}
