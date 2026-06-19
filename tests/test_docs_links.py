"""Validate local Markdown file and heading links in repo docs."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*$", re.MULTILINE)


def _markdown_files() -> list[Path]:
    roots = [REPO_ROOT, REPO_ROOT / "docs"]
    files: set[Path] = set()
    for root in roots:
        files.update(root.glob("*.md"))
    files.update((REPO_ROOT / "docs").rglob("*.md"))
    return sorted(files)


def _slug(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[`*_]", "", text).strip().lower()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    return re.sub(r"[\s-]+", "-", text).strip("-")


def _anchors(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    return {_slug(match.group(2)) for match in HEADING.finditer(text)}


def test_docs_markdown_local_links_exist() -> None:
    missing: list[str] = []
    anchor_cache: dict[Path, set[str]] = {}

    for source in _markdown_files():
        text = source.read_text(encoding="utf-8")
        for match in MARKDOWN_LINK.finditer(text):
            target = match.group(1).strip()
            if target.startswith(("http://", "https://", "mailto:", "#")) or "://" in target:
                continue

            target = target.split()[0]
            path_part, _, anchor = target.partition("#")
            if not path_part or path_part.startswith("/"):
                continue

            resolved = (source.parent / path_part).resolve()
            if not resolved.exists():
                missing.append(
                    f"{source.relative_to(REPO_ROOT)}: missing {target} -> {resolved}"
                )
                continue

            if anchor and resolved.suffix == ".md":
                anchor_cache.setdefault(resolved, _anchors(resolved))
                if anchor not in anchor_cache[resolved]:
                    missing.append(
                        f"{source.relative_to(REPO_ROOT)}: missing anchor {target}"
                    )

    assert not missing, "broken local Markdown links:\n" + "\n".join(missing)
