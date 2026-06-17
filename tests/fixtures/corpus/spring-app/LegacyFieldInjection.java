package com.example.shop.service;

import com.example.shop.repository.AuditRepository;
import com.example.shop.repository.OrderRepository;
import org.springframework.beans.factory.annotation.Autowired;

/**
 * Legacy field injection. No explicit constructor exists, so j2py's default
 * lowering would emit `self.repo: ... | None = None`. With `emit_init_param`
 * each @Autowired field is promoted to a required __init__ parameter, in
 * stable Java declaration order.
 */
public class LegacyFieldInjection {

    @Autowired
    private OrderRepository repo;

    @Autowired
    private AuditRepository audit;

    public void record(Long id) {
        audit.log(repo.findById(id));
    }
}
