from __future__ import annotations


class ClassicForMultipleInitUpdate:
    """Classic for-loops with multiple initializer and updater expressions."""

    def meet_in_middle(self, len2: int) -> bool:
        i = 1
        j = len2 - 1
        while i <= j:
            if i == j:
                return True
            i += 1
            j -= 1
        return False

    def sum_pair(self, limit: int) -> int:
        total = 0
        left = 0
        right = limit
        while left < right:
            total += left + right
            left += 1
            right -= 1
        return total

    def count_with_assignments(self, limit: int) -> int:
        i = None
        j = None
        seen = 0
        i = 0
        j = limit
        while i < j:
            seen += 1
            i += 1
            j -= 1
        return seen
