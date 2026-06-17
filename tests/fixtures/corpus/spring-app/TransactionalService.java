package com.example.shop.service;

import com.example.shop.domain.Order;
import com.example.shop.repository.OrderRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * @Transactional passthrough. The annotation lowers to a project-owned
 * `transactional` decorator that wraps the method in a session-scoped unit of
 * work. Spring AOP proxy semantics (propagation, rollback rules, isolation)
 * are explicit non-goals — see the cookbook "manual port" callouts.
 */
@Service
public class TransactionalService {

    private final OrderRepository repo;

    public TransactionalService(OrderRepository repo) {
        this.repo = repo;
    }

    @Transactional
    public Order createOrder(Order order) {
        return repo.save(order);
    }
}
