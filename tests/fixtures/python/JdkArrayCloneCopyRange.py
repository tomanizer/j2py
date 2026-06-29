from __future__ import annotations


class JdkArrayCloneCopyRange:

    def __init__(self, values: list[str]) -> None:
        self.values = list(values)

    def remaining(self, offset: int) -> list[str]:
        return list(self.values[offset:len(self.values)])
