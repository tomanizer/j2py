from __future__ import annotations


class AnonymousIteratorCapturesField:

    def __init__(self, values: list[str], offset: int) -> None:
        self.values = values
        self.offset = offset

    def iterator(self) -> object:

        _outer_self = self

        class _J2pyAnonymous1:
            def __init__(self):
                self.index: int = _outer_self.offset

            # @Override
            def has_next(self) -> bool:
                return self.index < len(_outer_self.values)

            # @Override
            def next_(self) -> str:
                if self.index >= len(_outer_self.values):
                    raise StopIteration()
                self.index += 1
                return _outer_self.values[(self.index - 1)]
        return _J2pyAnonymous1()
