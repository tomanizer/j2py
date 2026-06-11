from __future__ import annotations


class Fields:
    total: int = 0

    def __init__(self, count: int) -> None:
        self.name: str = "anonymous"
        self.enabled: bool = False
        self.count = count

    def get_name(self) -> str:
        return self.name
