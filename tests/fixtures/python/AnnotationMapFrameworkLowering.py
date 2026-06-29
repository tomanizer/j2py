from __future__ import annotations

from typing import TYPE_CHECKING

from zfixtures.db_base import Base
from zfixtures.db_tx import transactional
from zfixtures.spring_shim import mapped_controller
from zfixtures.web import router

if TYPE_CHECKING:
    from example.Order import Order
    from example.OrderRepository import OrderRepository


class Order:
    pass


class OrderRepository:

    def find_by_id(self, id_: int) -> Order:
        return Order()


# @RestController
# @Entity
@mapped_controller
class OrderController(Base):
    def __init__(self, repo: OrderRepository) -> None:
        # @Autowired
        # injected: OrderRepository repo
        self.repo: OrderRepository = repo

    # @Transactional
    # @GetMapping("/{id}")
    @transactional
    @router.get("/{id}")
    def get(self, id_: int) -> Order:
        return self.repo.find_by_id(id_)
