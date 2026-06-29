from __future__ import annotations


class ImplicitRuntimeExceptionBase(Exception):

    def __init__(self, message: str) -> None:
        super().__init__(message)
