from __future__ import annotations


class ThrowVarargsConstructor:

    def check(self, found: str, position: int, *expected: str) -> None:
        raise UnexpectedTokenException(found, position, *expected)


class UnexpectedTokenException(Exception):

    def __init__(self, found: str, position: int, *expected: str) -> None:
        super().__init__(found)
