from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Transactional:
    read_only: bool = False
    rollback_for: tuple[type[Any], ...] = ()


class Owner:
    pass


class AuditException:
    pass


class BaseService:

    def describe(self) -> str:
        return "base"


class OwnerService(BaseService):

    # @Transactional(readOnly=True)
    # read-only transaction
    def find_owner(self, id_: int) -> Owner:
        return Owner()

    def package_private_helper(self) -> None:
        pass

    # @Override
    def describe(self) -> str:
        return "owner"

    # @Transactional(rollbackFor=AuditException)
    # rollbackFor=AuditException
    def save_owner(self, owner: Owner) -> None:
        self.package_private_helper()
