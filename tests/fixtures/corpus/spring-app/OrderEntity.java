package com.example.shop.domain;

import javax.persistence.Column;
import javax.persistence.Entity;
import javax.persistence.GeneratedValue;
import javax.persistence.Id;
import javax.persistence.Table;

/**
 * JPA entity. The class-level @Entity maps to a SQLAlchemy declarative Base;
 * column-level annotations (@Id, @GeneratedValue, @Column) need richer
 * transforms than Tier 2 annotation_map provides and are a plugin (#337)
 * concern. See cookbook section 4 for the manual-port callouts.
 */
@Entity
@Table(name = "orders")
public class OrderEntity {

    @Id
    @GeneratedValue
    private Long id;

    @Column(name = "customer_name")
    private String customerName;

    private double total;

    public Long getId() {
        return id;
    }

    public String getCustomerName() {
        return customerName;
    }

    public double getTotal() {
        return total;
    }
}
