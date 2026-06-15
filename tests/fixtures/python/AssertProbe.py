from __future__ import annotations


class AssertProbe:
    """Tiny fixture: Java assert translates in the deterministic rule layer."""

    def check(self, value: int) -> None:
        assert value > 0, "must be positive"
