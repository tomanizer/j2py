package com.example;

import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.NamedParameterJdbcTemplate;
import org.springframework.jdbc.core.RowMapper;

public class JdbcTemplateSqlAlchemyScaffold {
    private final JdbcTemplate jdbcTemplate;
    private final NamedParameterJdbcTemplate namedJdbcTemplate;

    public JdbcTemplateSqlAlchemyScaffold(
            JdbcTemplate jdbcTemplate,
            NamedParameterJdbcTemplate namedJdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
        this.namedJdbcTemplate = namedJdbcTemplate;
    }

    public int rename(String firstName, long id) {
        return jdbcTemplate.update(
                "update owners set first_name = ? where id = ?",
                firstName,
                id);
    }

    public String findName(long id) {
        return jdbcTemplate.queryForObject(
                "select name from owners where id = ?",
                String.class,
                id);
    }

    public int namedRename(Map<String, Object> params) {
        return namedJdbcTemplate.update(
                "update owners set first_name = :firstName where id = :id",
                params);
    }

    public String namedFindName(Map<String, Object> params) {
        return namedJdbcTemplate.queryForObject(
                "select name from owners where id = :id",
                params,
                String.class);
    }

    public String mappedName(long id) {
        return jdbcTemplate.queryForObject(
                "select name from owners where id = ?",
                (rs, rowNum) -> rs.getString("name"),
                id);
    }
}
