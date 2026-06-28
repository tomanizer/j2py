"""Load and validate j2py wiring metadata sidecars."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from j2py.wire.schema import WiringSidecar
from j2py.wiring_contract import WIRING_METADATA_SCHEMA_VERSION


@dataclass(frozen=True)
class WiringLoadDiagnostic:
    """A non-fatal loader warning or fatal sidecar load error."""

    path: Path
    level: Literal["warning", "error"]
    message: str


@dataclass(frozen=True)
class WiringLoadResult:
    """Loaded wiring sidecars and diagnostics from a translated output tree."""

    sidecars: list[WiringSidecar]
    diagnostics: list[WiringLoadDiagnostic]

    @property
    def has_errors(self) -> bool:
        return any(diagnostic.level == "error" for diagnostic in self.diagnostics)


def discover_wiring_sidecars(translated_root: Path) -> list[Path]:
    """Return all wiring sidecars below a translated output root."""
    if not translated_root.exists() or not translated_root.is_dir():
        return []
    return sorted(translated_root.rglob("*.wiring.json"))


def load_wiring_sidecar(path: Path) -> tuple[WiringSidecar | None, list[WiringLoadDiagnostic]]:
    """Load one sidecar, returning diagnostics instead of raising for user data errors."""
    diagnostics: list[WiringLoadDiagnostic] = []
    if not path.exists():
        return None, [
            WiringLoadDiagnostic(
                path=path,
                level="error",
                message=f"sidecar not found: {path}",
            ),
        ]
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, [
            WiringLoadDiagnostic(
                path=path,
                level="error",
                message=f"malformed JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}",
            ),
        ]

    try:
        sidecar = WiringSidecar.model_validate(raw)
    except ValidationError as exc:
        return None, [
            WiringLoadDiagnostic(
                path=path,
                level="error",
                message=f"invalid wiring sidecar schema: {exc.errors()[0]['msg']}",
            ),
        ]

    if sidecar.schema_version != WIRING_METADATA_SCHEMA_VERSION:
        diagnostics.append(
            WiringLoadDiagnostic(
                path=path,
                level="warning",
                message=(
                    f"unknown wiring schema_version {sidecar.schema_version}; "
                    f"expected {WIRING_METADATA_SCHEMA_VERSION}"
                ),
            ),
        )
    return sidecar, diagnostics


def load_wiring_sidecars(translated_root: Path) -> WiringLoadResult:
    """Load all sidecars below a translated output root."""
    if not translated_root.exists():
        return WiringLoadResult(
            sidecars=[],
            diagnostics=[
                WiringLoadDiagnostic(
                    path=translated_root,
                    level="error",
                    message=f"translated output directory not found: {translated_root}",
                ),
            ],
        )
    if not translated_root.is_dir():
        return WiringLoadResult(
            sidecars=[],
            diagnostics=[
                WiringLoadDiagnostic(
                    path=translated_root,
                    level="error",
                    message=f"translated output path is not a directory: {translated_root}",
                ),
            ],
        )

    sidecars: list[WiringSidecar] = []
    diagnostics: list[WiringLoadDiagnostic] = []
    for path in discover_wiring_sidecars(translated_root):
        sidecar, sidecar_diagnostics = load_wiring_sidecar(path)
        diagnostics.extend(sidecar_diagnostics)
        if sidecar is not None:
            sidecars.append(sidecar)
    return WiringLoadResult(sidecars=sidecars, diagnostics=diagnostics)


def spring_elements(sidecars: Iterable[WiringSidecar]) -> list[tuple[WiringSidecar, int]]:
    """Return sidecar/element-index pairs that carry Spring metadata."""
    return [
        (sidecar, index)
        for sidecar in sidecars
        for index, element in enumerate(sidecar.elements)
        if element.spring
    ]
