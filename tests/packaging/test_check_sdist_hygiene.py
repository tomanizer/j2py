from __future__ import annotations

import importlib.util
import tarfile
from io import BytesIO
from pathlib import Path


def _load_hygiene_module():
    path = Path(__file__).resolve().parents[2] / "scripts/packaging/check_sdist_hygiene.py"
    spec = importlib.util.spec_from_file_location("check_sdist_hygiene", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write_archive(path: Path, names: list[str]) -> None:
    with tarfile.open(path, "w:gz") as archive:
        for name in names:
            payload = b"placeholder"
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, BytesIO(payload))


def test_forbidden_entries_detects_local_and_generated_state(tmp_path: Path) -> None:
    module = _load_hygiene_module()
    archive_path = tmp_path / "j2py_converter-1.0.0.tar.gz"
    entries = [
        "j2py_converter-1.0.0/README.md",
        "j2py_converter-1.0.0/.claude/worktrees/issue/main.py",
        "j2py_converter-1.0.0/.codex/session.json",
        "j2py_converter-1.0.0/.claire/state.json",
        "j2py_converter-1.0.0/.venv/bin/python",
        "j2py_converter-1.0.0/.corpus/guava/File.java",
        "j2py_converter-1.0.0/corpus-reports/report.json",
        "j2py_converter-1.0.0/.mypy_cache-3.11/module.data.json",
        "j2py_converter-1.0.0/j2py/__pycache__-old/module.pyc",
        "j2py_converter-1.0.0/packages/j2py-vscode/node_modules/pkg/index.js",
        "j2py_converter-1.0.0/packages/j2py-vscode/out/extension.js",
        "j2py_converter-1.0.0/packages/j2py-vscode/j2py-0.1.0.vsix",
    ]
    _write_archive(archive_path, entries)

    assert module.forbidden_entries(archive_path) == entries[1:]


def test_forbidden_entries_allows_clean_archive(tmp_path: Path) -> None:
    module = _load_hygiene_module()
    archive_path = tmp_path / "j2py_converter-1.0.0.tar.gz"
    _write_archive(
        archive_path,
        [
            "j2py_converter-1.0.0/README.md",
            "j2py_converter-1.0.0/j2py/__init__.py",
            "j2py_converter-1.0.0/tests/test_cli.py",
            "j2py_converter-1.0.0/packages/j2py-vscode/src/extension.ts",
        ],
    )

    assert module.forbidden_entries(archive_path) == []
