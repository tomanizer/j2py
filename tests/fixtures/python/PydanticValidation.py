from __future__ import annotations

from pydantic import BaseModel, Field


class CreateOwnerForm(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=30)
    age: int = Field(0, ge=0, le=150)
    retries: int = Field(3, le=10)
    code: str = Field(..., min_length=1, pattern='[A-Z]+')
    nickname: str | None = Field(None, max_length=60)
    slug: str | None = Field(None, pattern='[a-z]+')
    # @Digits(integer=3, fraction=2)
    price: int = Field(0)
