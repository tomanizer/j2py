from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session


class Owner:
    pass


class OwnerRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_last_name(self, last_name: str) -> list[Owner]:
        # TODO(j2py): translate JPQL query
        # JPQL: SELECT o FROM Owner o WHERE o.lastName = :lastName
        raise NotImplementedError

    def find_by_city(self, city: str) -> list[Owner]:
        # TODO(j2py): translate Spring Data derived query method findByCity
        raise NotImplementedError

    def find_by_id(self, id: int) -> Owner | None:
        return self._session.get(Owner, id)

    def find_all(self) -> list[Owner]:
        return list(self._session.execute(select(Owner)).scalars())

    def save(self, entity: Owner) -> Owner:
        self._session.add(entity)
        self._session.flush()
        return entity

    def delete(self, entity: Owner) -> None:
        self._session.delete(entity)

    def exists_by_id(self, id: int) -> bool:
        return self._session.get(Owner, id) is not None

    def count(self) -> int:
        return self._session.scalar(select(func.count()).select_from(Owner)) or 0
