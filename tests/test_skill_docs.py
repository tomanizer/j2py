"""Validate tracked Cursor agent skill docs."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / ".cursor" / "skills"
LINK_PATTERN = re.compile(r"\]\((\.\./[^)#]+)(?:#[^)]+)?\)")
FRONTMATTER_NAME = re.compile(r"^name:\s*(.+)$", re.MULTILINE)
FRONTMATTER_DESC = re.compile(r"^description:\s*>-\s*$|^description:\s*(.+)$", re.MULTILINE)


def _skill_files() -> list[Path]:
    return sorted(SKILLS_DIR.glob("*/SKILL.md"))


def _resolve_link(skill_path: Path, target: str) -> Path:
    return (skill_path.parent / target).resolve()


@pytest.mark.parametrize("skill_path", _skill_files(), ids=lambda p: p.parent.name)
def test_skill_frontmatter(skill_path: Path) -> None:
    text = skill_path.read_text(encoding="utf-8")
    assert text.startswith("---"), skill_path
    assert FRONTMATTER_NAME.search(text), f"missing name: {skill_path}"
    assert "description:" in text, f"missing description: {skill_path}"


@pytest.mark.parametrize("skill_path", _skill_files(), ids=lambda p: p.parent.name)
def test_skill_markdown_links_exist(skill_path: Path) -> None:
    text = skill_path.read_text(encoding="utf-8")
    missing: list[str] = []
    for match in LINK_PATTERN.finditer(text):
        target = match.group(1)
        if target.startswith("http"):
            continue
        resolved = _resolve_link(skill_path, target)
        if not resolved.exists():
            missing.append(f"{target} -> {resolved}")
    assert not missing, f"{skill_path.relative_to(REPO_ROOT)} broken links:\n" + "\n".join(missing)


def test_skills_readme_lists_all_skills() -> None:
    readme = (SKILLS_DIR / "README.md").read_text(encoding="utf-8")
    for skill_path in _skill_files():
        skill_name = skill_path.parent.name
        assert f"]({skill_name}/SKILL.md)" in readme, f"README missing {skill_name}"
