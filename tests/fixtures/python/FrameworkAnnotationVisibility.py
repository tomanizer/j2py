from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from example.OrderRepository import OrderRepository


@dataclass(frozen=True)
class Service:
    pass


@dataclass(frozen=True)
class RestController:
    pass


@dataclass(frozen=True)
class Autowired:
    pass


@dataclass(frozen=True)
class Entity:
    pass


class OrderRepository(Protocol):
    pass


# @Service
# @RestController
class OrderController:
    def __init__(self) -> None:
        # @Autowired
        self.repo: OrderRepository | None = None


# @Entity
class User:
    def __init__(self) -> None:
        self.id_: int | None = None
