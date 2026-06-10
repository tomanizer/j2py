package org.springframework.core.convert;

import java.util.List;
import java.util.stream.Collectors;

public class Functional {

    public List<String> names(List<Class<?>> types) {
        return types.stream()
                .map(Class::getName)
                .filter(name -> !name.isEmpty())
                .collect(Collectors.toList());
    }
}
