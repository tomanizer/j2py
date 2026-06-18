from __future__ import annotations

from pydantic import BaseModel, Field


class OwnerController:

    # @PostMapping("/owners")
    def process_creation_form(self, form: OwnerRequest) -> OwnerRequest:
        return form


class OwnerRequest(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=30)
    last_name: str | None = None
