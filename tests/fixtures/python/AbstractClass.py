from __future__ import annotations

from abc import ABC, abstractmethod


class Shape(ABC):
    def __init__(self) -> None:
        self.label: str | None = None

    @abstractmethod
    def area(self) -> float:
        ...

    @abstractmethod
    def perimeter(self) -> float:
        ...

    def color(self) -> str:
        return self.label
