"""FastAPI wiring generation target placeholder."""

from __future__ import annotations

from pathlib import Path

from j2py.wire.schema import WiringSidecar


def generate_fastapi_wiring(
    sidecars: list[WiringSidecar],
    *,
    output_dir: Path,
) -> None:
    """Reserve the FastAPI generator surface for issue #529."""
    _ = (sidecars, output_dir)
    raise NotImplementedError("FastAPI wiring generation is tracked by issue #529")
