from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from com.example.Task import Task


class Task(Protocol):
    def run(self) -> None: ...


class OuterThisCapture:
    def __init__(self) -> None:
        self.name: str | None = None

    class InnerTask:
        def __init__(self, _outer_self: object) -> None:
            self._outer_self = _outer_self

        def owner(self) -> str:
            return self._outer_self.name

    def create_task(self) -> Task:

        _outer_self = self

        class _J2pyAnonymous1(Task):
            # @Override
            def run(self) -> None:
                print(_outer_self.name)
                _outer_self.process()
        return _J2pyAnonymous1()

    def process(self) -> None:
        print(self.name)

    def create_inner(self) -> OuterThisCapture.InnerTask:
        return self.InnerTask(self)
