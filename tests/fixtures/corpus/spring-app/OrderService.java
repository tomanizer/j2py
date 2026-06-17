package com.example.shop.service;

import com.example.shop.domain.Order;
import com.example.shop.repository.OrderRepository;
import org.springframework.stereotype.Service;

/**
 * Modern Spring constructor injection. Translates almost cleanly today:
 * the explicit constructor becomes __init__ with typed parameters.
 */
@Service
public class OrderService {

    private final OrderRepository repo;

    public OrderService(OrderRepository repo) {
        this.repo = repo;
    }

    public Order findById(Long id) {
        return repo.findById(id);
    }

    public Order save(Order order) {
        return repo.save(order);
    }

    public void deleteById(Long id) {
        repo.deleteById(id);
    }
}
