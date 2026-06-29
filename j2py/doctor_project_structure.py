"""Deterministic Java project-structure detection for doctor assessments."""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from pathlib import Path
from typing import Any

_BUILD_DIR_NAMES = {".git", ".gradle", ".idea", "build", "target", "out"}
_MAVEN_SOURCE_PROPERTIES = (
    "maven.compiler.release",
    "maven.compiler.source",
    "maven.compiler.target",
)
_GRADLE_INCLUDE_PATTERN = re.compile(r"include\s*(?:\((?P<call>[^)]*)\)|(?P<bare>[^\n]+))")
_GRADLE_LANGUAGE_PATTERNS = (
    re.compile(r"(?:sourceCompatibility|targetCompatibility)\s*=\s*['\"]?([^'\"\s]+)"),
    re.compile(r"JavaVersion\.VERSION_(\d+(?:_\d+)?)"),
    re.compile(r"JavaLanguageVersion\.of\((\d+)\)"),
)


def detect_project_structure(source: Path, java_files: Iterable[Path]) -> dict[str, Any]:
    """Return deterministic project metadata without executing build tools."""
    assessment_root = source if source.is_dir() else source.parent
    assessment_root = assessment_root.resolve()
    project_root = _find_project_root(assessment_root)
    java_file_list = [path.resolve() for path in java_files]
    module_bases = _module_bases(project_root)
    if not module_bases:
        module_bases = [project_root]

    modules = [
        _module_payload(
            module_base,
            assessment_root=assessment_root,
            java_files=java_file_list,
            module_bases=module_bases,
        )
        for module_base in sorted(
            set(module_bases),
            key=lambda path: _relative_path(path, project_root),
        )
    ]
    build_systems = sorted({system for module in modules for system in module["build_systems"]})
    language_levels = [
        level for module in modules if (level := module.get("java_language_level")) is not None
    ]
    warnings = _structure_warnings(project_root, modules)

    return {
        "root": _relative_path(project_root, assessment_root),
        "build_systems": build_systems,
        "java_language_level": language_levels[0] if language_levels else None,
        "modules": modules,
        "warnings": warnings,
    }


def file_project_structure(
    path: Path,
    project_structure: dict[str, Any],
    *,
    assessment_root: Path,
) -> dict[str, str | None]:
    """Classify a Java file by detected module and source root."""
    resolved = path.resolve()
    root = assessment_root.resolve()
    candidates: list[tuple[int, dict[str, str | None]]] = []
    for module in project_structure.get("modules", []):
        module_path = str(module.get("path", "."))
        module_root = _resolve_relative(root, module_path)
        root_matches: list[tuple[str, str]] = []
        root_matches.extend((item, "main") for item in module.get("source_roots", []))
        root_matches.extend((item, "test") for item in module.get("test_roots", []))
        root_matches.extend(
            (item, "generated") for item in module.get("generated_source_roots", [])
        )
        for root_path, source_set in root_matches:
            source_root = _resolve_relative(root, root_path)
            if _is_relative_to(resolved, source_root):
                candidates.append(
                    (
                        len(source_root.parts),
                        {
                            "module": str(module.get("name", "")),
                            "module_path": module_path,
                            "source_root": root_path,
                            "source_set": source_set,
                        },
                    )
                )
        if _is_relative_to(resolved, module_root):
            candidates.append(
                (
                    len(module_root.parts),
                    {
                        "module": str(module.get("name", "")),
                        "module_path": module_path,
                        "source_root": None,
                        "source_set": "unknown",
                    },
                )
            )
    if candidates:
        return sorted(candidates, key=lambda item: item[0], reverse=True)[0][1]
    return {
        "module": None,
        "module_path": None,
        "source_root": None,
        "source_set": "unknown",
    }


def _find_project_root(assessment_root: Path) -> Path:
    for candidate in (assessment_root, *assessment_root.parents):
        if _build_files(candidate):
            return candidate
    return assessment_root


def _module_bases(project_root: Path) -> list[Path]:
    bases: set[Path] = {project_root}
    bases.update(_maven_module_bases(project_root))
    bases.update(_gradle_module_bases(project_root))
    bases.update(_child_build_module_bases(project_root))
    return sorted(bases, key=lambda path: _relative_path(path, project_root))


def _maven_module_bases(project_root: Path) -> set[Path]:
    pom = project_root / "pom.xml"
    if not pom.is_file():
        return set()
    root = _parse_xml(pom)
    if root is None:
        return set()
    modules: set[Path] = set()
    for module in _xml_children(root, "modules"):
        for item in _xml_children(module, "module"):
            text = (item.text or "").strip()
            if text:
                modules.add((project_root / text).resolve())
    return modules


def _gradle_module_bases(project_root: Path) -> set[Path]:
    settings = [
        path
        for path in (project_root / "settings.gradle", project_root / "settings.gradle.kts")
        if path.is_file()
    ]
    modules: set[Path] = set()
    for path in settings:
        for name in _gradle_includes(path.read_text(encoding="utf-8", errors="replace")):
            module_path = name.strip(":").replace(":", "/")
            if module_path:
                modules.add((project_root / module_path).resolve())
    return modules


def _child_build_module_bases(project_root: Path) -> set[Path]:
    modules: set[Path] = set()
    for path in project_root.rglob("*"):
        if not path.is_dir() or path == project_root or _is_ignored_path(path, project_root):
            continue
        if _build_files(path):
            modules.add(path.resolve())
    return modules


def _module_payload(
    module_base: Path,
    *,
    assessment_root: Path,
    java_files: list[Path],
    module_bases: list[Path],
) -> dict[str, Any]:
    build_files = _build_files(module_base)
    build_systems = _build_systems(build_files)
    owned_java_files = _module_owned_java_files(module_base, java_files, module_bases)
    source_roots, test_roots, generated_source_roots = _source_roots(module_base, owned_java_files)
    language_level = _java_language_level(module_base)
    return {
        "name": module_base.name or ".",
        "path": _relative_path(module_base, assessment_root),
        "build_systems": build_systems,
        "build_files": [_relative_path(path, assessment_root) for path in build_files],
        "source_roots": [_relative_path(path, assessment_root) for path in source_roots],
        "test_roots": [_relative_path(path, assessment_root) for path in test_roots],
        "generated_source_roots": [
            _relative_path(path, assessment_root) for path in generated_source_roots
        ],
        "java_language_level": language_level,
    }


def _module_owned_java_files(
    module_base: Path,
    java_files: list[Path],
    module_bases: list[Path],
) -> list[Path]:
    child_modules = [
        base for base in module_bases if base != module_base and _is_relative_to(base, module_base)
    ]
    return [
        path
        for path in java_files
        if _is_relative_to(path, module_base)
        and not any(_is_relative_to(path, child_module) for child_module in child_modules)
    ]


def _source_roots(
    module_base: Path,
    java_files: list[Path],
) -> tuple[list[Path], list[Path], list[Path]]:
    source_roots = _existing_dirs(module_base, ("src/main/java",))
    test_roots = _existing_dirs(module_base, ("src/test/java",))
    generated_roots = _generated_roots(module_base)
    if not source_roots:
        module_java_files = [path for path in java_files if _is_relative_to(path, module_base)]
        if module_java_files:
            source_roots = [_common_java_root(module_base, module_java_files)]
    return (
        sorted(set(source_roots), key=lambda path: _relative_path(path, module_base)),
        sorted(set(test_roots), key=lambda path: _relative_path(path, module_base)),
        sorted(set(generated_roots), key=lambda path: _relative_path(path, module_base)),
    )


def _existing_dirs(module_base: Path, relative_paths: Iterable[str]) -> list[Path]:
    return [
        (module_base / item).resolve() for item in relative_paths if (module_base / item).is_dir()
    ]


def _generated_roots(module_base: Path) -> list[Path]:
    candidates = (
        "target/generated-sources",
        "target/generated-test-sources",
        "build/generated",
        "build/generated/sources/annotationProcessor/java/main",
        "build/generated/sources/annotationProcessor/java/test",
    )
    return _existing_dirs(module_base, candidates)


def _common_java_root(module_base: Path, java_files: list[Path]) -> Path:
    return module_base.resolve()


def _build_files(path: Path) -> list[Path]:
    names = (
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "settings.gradle",
        "settings.gradle.kts",
    )
    return sorted((path / name).resolve() for name in names if (path / name).is_file())


def _build_systems(build_files: list[Path]) -> list[str]:
    systems = set()
    for path in build_files:
        if path.name == "pom.xml":
            systems.add("maven")
        if path.name.endswith(".gradle") or path.name.endswith(".gradle.kts"):
            systems.add("gradle")
    return sorted(systems)


def _java_language_level(module_base: Path) -> str | None:
    pom_level = _maven_java_language_level(module_base / "pom.xml")
    if pom_level is not None:
        return pom_level
    for path in (module_base / "build.gradle", module_base / "build.gradle.kts"):
        if path.is_file():
            gradle_level = _gradle_java_language_level(path)
            if gradle_level is not None:
                return gradle_level
    return None


def _maven_java_language_level(pom: Path) -> str | None:
    if not pom.is_file():
        return None
    root = _parse_xml(pom)
    if root is None:
        return None
    properties = next(iter(_xml_children(root, "properties")), None)
    if properties is not None:
        values = {
            _xml_tag(child): (child.text or "").strip()
            for child in list(properties)
            if (child.text or "").strip()
        }
        for key in _MAVEN_SOURCE_PROPERTIES:
            if key in values:
                return _normalize_java_level(values[key])
    for plugin in root.iter():
        if _xml_tag(plugin) != "plugin":
            continue
        artifact = next(iter(_xml_children(plugin, "artifactId")), None)
        if artifact is None or (artifact.text or "").strip() != "maven-compiler-plugin":
            continue
        config = next(iter(_xml_children(plugin, "configuration")), None)
        if config is None:
            continue
        for key in ("release", "source", "target"):
            child = next(iter(_xml_children(config, key)), None)
            if child is not None and (child.text or "").strip():
                return _normalize_java_level((child.text or "").strip())
    return None


def _gradle_java_language_level(path: Path) -> str | None:
    text = path.read_text(encoding="utf-8", errors="replace")
    for pattern in _GRADLE_LANGUAGE_PATTERNS:
        match = pattern.search(text)
        if match:
            return _normalize_java_level(match.group(1))
    return None


def _gradle_includes(text: str) -> list[str]:
    modules: list[str] = []
    for match in _GRADLE_INCLUDE_PATTERN.finditer(text):
        expression = match.group("call") or match.group("bare") or ""
        modules.extend(re.findall(r"['\"](:?[\w./:-]+)['\"]", expression))
    return sorted(set(modules))


def _structure_warnings(project_root: Path, modules: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    levels = sorted(
        {
            str(module["java_language_level"])
            for module in modules
            if module.get("java_language_level") is not None
        }
    )
    if len(levels) > 1:
        warnings.append(
            "multiple Java language levels detected under "
            f"{_relative_path(project_root, project_root)}"
        )
    return warnings


def _parse_xml(path: Path) -> ET.Element | None:
    try:
        return ET.parse(path).getroot()
    except ET.ParseError:
        return None


def _xml_children(node: ET.Element, tag: str) -> list[ET.Element]:
    return [child for child in list(node) if _xml_tag(child) == tag]


def _xml_tag(node: ET.Element) -> str:
    return node.tag.rsplit("}", 1)[-1]


def _normalize_java_level(value: str) -> str:
    value = value.strip().removeprefix("VERSION_").replace("_", ".")
    if value.startswith("1."):
        return value.split(".", 1)[1]
    return value


def _is_ignored_path(path: Path, root: Path) -> bool:
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return False
    return any(part in _BUILD_DIR_NAMES for part in parts)


def _resolve_relative(root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path.resolve()
    return (root / value).resolve()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _relative_path(path: Path, root: Path) -> str:
    path = path.resolve()
    root = root.resolve()
    if path == root:
        return "."
    try:
        return str(path.relative_to(root))
    except ValueError:
        return os.path.relpath(path, root)
