"""Pydantic models for generic j2py wiring sidecars."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class WiringElement(BaseModel):
    """One generic framework metadata record emitted by j2py."""

    model_config = ConfigDict(extra="forbid")

    plugin: str
    kind: Literal["class", "field", "method", "constructor"]
    java_name: str
    python_name: str
    annotations: list[dict[str, object]] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)

    @property
    def spring(self) -> dict[str, object]:
        """Return Spring profile metadata, if present."""
        spring = self.metadata.get("spring")
        return spring if isinstance(spring, dict) else {}


class WiringSidecar(BaseModel):
    """Generic top-level wiring sidecar shape written by j2py."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int
    source: str
    output: str
    elements: list[WiringElement]

    def python_module(self, translated_root: Path) -> str:
        """Derive the Python module for this sidecar from output path and translated root."""
        output = Path(self.output)
        relative = output.relative_to(translated_root).with_suffix("")
        module = ".".join(relative.parts)
        return module.removesuffix(".__init__")
