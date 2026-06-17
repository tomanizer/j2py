from __future__ import annotations


class StreamFlatMap:
    class Item:

        def get_tags(self) -> list[str]:
            return None

    def flatten_nested(self, nested: list[list[str]]) -> list[str]:
        return [nested_item for nested in nested for nested_item in nested]

    def collect_tags(self, items: list[Item]) -> set[str]:
        return {item_item for item in items for item_item in item.get_tags()}
