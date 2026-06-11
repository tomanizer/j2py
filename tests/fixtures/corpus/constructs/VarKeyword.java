package org.springframework.example;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * Minimal example for local variable type inference (var, Java 10+).
 * Used heavily in modern Spring code for readability with generics and streams.
 */
public class VarKeyword {

    public List<String> processWithVar(List<Map<String, Object>> data) {
        var results = new ArrayList<String>();
        for (var item : data) {
            var name = (String) item.get("name");
            var count = ((Number) item.getOrDefault("count", 0)).intValue();
            if (count > 0 && name != null) {
                var formatted = name.trim().toLowerCase();
                results.add(formatted);
            }
        }
        return results;
    }

    public String inferInStream(List<Integer> numbers) {
        var sum = numbers.stream()
                .mapToInt(Integer::intValue)
                .sum();
        var average = numbers.isEmpty() ? 0.0 : (double) sum / numbers.size();
        var message = "sum=" + sum + ", avg=" + average;
        return message;
    }
}
