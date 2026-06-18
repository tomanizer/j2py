package com.example;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public class RawJdbcBoundary {
    private final DataSource dataSource;

    public RawJdbcBoundary(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public String loadName(Connection connection, long id) throws SQLException {
        PreparedStatement statement = connection.prepareStatement("select name from owners where id = ?");
        statement.setLong(1, id);
        ResultSet resultSet = statement.executeQuery();
        if (resultSet.next()) {
            return resultSet.getString("name");
        }
        throw new SQLException("missing owner");
    }

    public Connection open(String url) throws SQLException {
        return DriverManager.getConnection(url);
    }

    public DataSource dataSource() {
        return dataSource;
    }
}
