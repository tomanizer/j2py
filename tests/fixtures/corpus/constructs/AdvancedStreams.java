package org.springframework.example;

import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * Minimal example for advanced stream pipelines.
 * Covers flatMap, reduce, complex collectors (groupingBy with downstream),
 * block lambdas in streams, and long chains.
 * Common in Spring data processing, repository projections, etc.
 */
public class AdvancedStreams {

    record Item(String category, int value) {}

    public List<String> flatMapExample(List<List<String>> nested) {
        return nested.stream()
                .flatMap(List::stream)
                .map(String::toUpperCase)
                .collect(Collectors.toList());
    }

    public int reduceExample(List<Integer> numbers) {
        return numbers.stream()
                .reduce(0, Integer::sum);
    }

    public Map<String, List<Item>> groupingByWithDownstream(List<Item> items) {
        return items.stream()
                .collect(Collectors.groupingBy(
                        Item::category,
                        Collectors.mapping(i -> i, Collectors.toList())
                ));
    }

    public String longChainWithBlockLambda(List<String> inputs) {
        return inputs.stream()
                .filter(s -> {
                    String trimmed = s.trim();
                    return !trimmed.isEmpty() && trimmed.length() > 3;
                })
                .map(s -> s.toLowerCase())
                .sorted()
                .collect(Collectors.joining(", "));
    }
}
