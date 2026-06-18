from __future__ import annotations

from pydantic import BaseModel, Field


class CreateOwnerForm(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=30)
    age: int = Field(..., ge=0, le=150)
    code: str = Field(..., min_length=1, pattern='[A-Z]+')
    # @Digits(integer=3, fraction=2)
    price: int = Field(...)
