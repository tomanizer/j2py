package com.example;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.BeanPropertyRowMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.NamedParameterJdbcTemplate;
import org.springframework.jdbc.core.RowMapper;

public class JdbcRowMapperScaffold {
    private final JdbcTemplate jdbcTemplate;
    private final NamedParameterJdbcTemplate namedJdbcTemplate;

    public JdbcRowMapperScaffold(
            JdbcTemplate jdbcTemplate,
            NamedParameterJdbcTemplate namedJdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
        this.namedJdbcTemplate = namedJdbcTemplate;
    }

    public List<Owner> allOwners() {
        return jdbcTemplate.query(
                "select id, first_name, last_name from owners",
                (rs, rowNum) -> new Owner(
                        rs.getLong("id"),
                        rs.getString("first_name"),
                        rs.getString("last_name")));
    }

    public Owner ownerById(long id) {
        return jdbcTemplate.queryForObject(
                "select id, first_name, last_name from owners where id = ?",
                (rs, rowNum) -> new Owner(
                        rs.getLong("id"),
                        rs.getString("first_name"),
                        rs.getString("last_name")),
                id);
    }

    public Owner anonymousOwner(long id) {
        return jdbcTemplate.queryForObject(
                "select id, first_name, last_name from owners where id = ?",
                new RowMapper<Owner>() {
                    public Owner mapRow(ResultSet rs, int rowNum) throws SQLException {
                        return new Owner(
                                rs.getLong("id"),
                                rs.getString("first_name"),
                                rs.getString("last_name"));
                    }
                },
                id);
    }

    public List<Owner> beanOwners() {
        return jdbcTemplate.query(
                "select id, first_name, last_name from owners",
                BeanPropertyRowMapper.newInstance(Owner.class));
    }

    public Owner namedBeanOwner(Map<String, Object> params) {
        return namedJdbcTemplate.queryForObject(
                "select id, first_name, last_name from owners where id = :id",
                params,
                new BeanPropertyRowMapper<>(Owner.class));
    }

    public Owner unsupportedOwner(long id) {
        return jdbcTemplate.queryForObject(
                "select id, first_name, last_name from owners where id = ?",
                this::mapOwner,
                id);
    }

    private Owner mapOwner(ResultSet rs, int rowNum) throws SQLException {
        return new Owner(
                rs.getLong("id"),
                rs.getString("first_name"),
                rs.getString("last_name"));
    }
}
