import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

public class StreamFlatMap {
    static class Item {
        List<String> getTags() {
            return null;
        }
    }

    public List<String> flattenNested(List<List<String>> nested) {
        return nested.stream()
                .flatMap(group -> group.stream())
                .collect(Collectors.toList());
    }

    public Set<String> collectTags(List<Item> items) {
        return items.stream()
                .flatMap(item -> item.getTags().stream())
                .collect(Collectors.toSet());
    }
}
