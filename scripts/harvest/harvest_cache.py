"""Skip re-harvesting sources already recorded at the same Java content hash."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from j2py.llm.harvest import harvest_records_path, latest_harvest_records, load_harvest_records


@dataclass(frozen=True)
class HarvestCacheEntry:
    source_path: str
    java_sha256: str
    status: str


def java_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalize_source_path(path: Path) -> str:
    return str(path.resolve())


def load_harvest_cache(records_path: Path | None = None) -> dict[str, HarvestCacheEntry]:
    """Index latest harvest row per ``source_path``."""
    path = records_path or harvest_records_path()
    index: dict[str, HarvestCacheEntry] = {}
    for record in latest_harvest_records(load_harvest_records(path)):
        source = record.get("source_path")
        digest = record.get("java_sha256")
        if not isinstance(source, str) or not isinstance(digest, str):
            continue
        try:
            key = _normalize_source_path(Path(source))
        except OSError:
            key = source
        index[key] = HarvestCacheEntry(
            source_path=key,
            java_sha256=digest,
            status=str(record.get("status", "open")),
        )
    return index


def should_skip_harvest(
    path: Path,
    cache: dict[str, HarvestCacheEntry],
    *,
    force: bool = False,
) -> bool:
    """Return True when this file was already LLM-harvested at the current content hash."""
    if force or not path.is_file():
        return False
    key = _normalize_source_path(path)
    entry = cache.get(key)
    if entry is None:
        return False
    if entry.status == "resolved":
        return True
    try:
        current = java_sha256(path)
    except OSError:
        return False
    return current == entry.java_sha256


def filter_uncached_paths(
    paths: list[Path],
    cache: dict[str, HarvestCacheEntry],
    *,
    force: bool = False,
) -> tuple[list[Path], list[Path]]:
    """Split paths into (to_harvest, cache_skipped)."""
    if force:
        return paths, []
    to_harvest: list[Path] = []
    skipped: list[Path] = []
    for path in paths:
        if should_skip_harvest(path, cache, force=False):
            skipped.append(path)
        else:
            to_harvest.append(path)
    return to_harvest, skipped


def sync_queue_offset(
    queue_paths: list[Path],
    cache: dict[str, HarvestCacheEntry],
    current_offset: int,
) -> int:
    """Advance offset past queue entries already present in the harvest cache."""
    offset = max(0, current_offset)
    while offset < len(queue_paths):
        path = queue_paths[offset]
        if not should_skip_harvest(path, cache, force=False):
            break
        offset += 1
    return offset
