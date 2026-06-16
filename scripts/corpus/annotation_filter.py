"""Annotation-aware pre-filtering for enterprise Spring corpus presets.

Matches ``@Annotation`` uses in Java source (simple or scoped annotation names).
Used by ``translate_corpus.collect_java_files`` when a preset sets
``require_annotations``.
"""

from __future__ import annotations

import re
from collections import Counter

# Default enterprise annotation names for spring-app-dense (#336).
DEFAULT_ENTERPRISE_ANNOTATIONS: tuple[str, ...] = (
    "RestController",
    "Controller",
    "RequestMapping",
    "GetMapping",
    "PostMapping",
    "PutMapping",
    "DeleteMapping",
    "PathVariable",
    "RequestBody",
    "Service",
    "Repository",
    "Component",
    "Configuration",
    "Bean",
    "Autowired",
    "Qualifier",
    "Value",
    "Entity",
    "Table",
    "Transactional",
    "OneToMany",
    "ManyToOne",
    "JoinColumn",
)


def _annotation_pattern(name: str) -> re.Pattern[str]:
    """Match @Name or @package.path.Name (not import lines or identifiers in code)."""
    return re.compile(rf"@(?:[\w.]+\.)?{re.escape(name)}\b")


def annotation_hits(text: str, names: tuple[str, ...]) -> dict[str, int]:
    """Return per-annotation occurrence counts in ``text``."""
    hits: dict[str, int] = {}
    for name in names:
        count = len(_annotation_pattern(name).findall(text))
        if count:
            hits[name] = count
    return hits


def total_annotation_hits(text: str, names: tuple[str, ...]) -> int:
    return sum(annotation_hits(text, names).values())


def passes_annotation_filter(
    text: str,
    *,
    require_annotations: tuple[str, ...],
    min_annotation_hits: int,
) -> bool:
    if not require_annotations or min_annotation_hits <= 0:
        return True
    return total_annotation_hits(text, require_annotations) >= min_annotation_hits


def annotation_family_file_counts(
    file_texts: list[tuple[str, str]],
    *,
    require_annotations: tuple[str, ...],
) -> dict[str, int]:
    """Count files containing at least one hit per annotation name."""
    counts: Counter[str] = Counter()
    for _path, text in file_texts:
        for name in annotation_hits(text, require_annotations):
            counts[name] += 1
    return dict(sorted(counts.items()))
