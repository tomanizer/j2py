"""Enforce the core <-> j2py-wire packaging boundary at import level.

The j2py core translator and the ``j2py.wire`` sidecar consumer are deliberately kept on
opposite sides of a serialized contract (``*.wiring.json``). This test locks the seam so a
future package split stays mechanical:

1. Core never depends on the consumer: nothing under ``j2py/`` (outside ``j2py/wire/``) may
   import ``j2py.wire`` -- the dependency arrow only points consumer -> core.
2. The consumer touches core only through the public facade: modules under ``j2py/wire/``
   may import core *only* via ``j2py.wiring_contract`` (plus their own package), never
   ``j2py.pipeline`` or ``j2py.translate.*`` Internal surfaces.
3. Core never depends on the framework producer plugins: nothing under ``j2py/`` (outside
   ``j2py/framework_plugins/``) may import ``j2py.framework_plugins`` -- plugins are
   config-injected and import core, but core stays framework-neutral and never imports a
   plugin. This is one-directional by design: plugins may reach into core internals; the
   ban is only on the reverse edge.

See ADR 0022 / ADR 0024 and docs/developer/API_STABILITY.md.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PKG_ROOT = REPO_ROOT / "j2py"

WIRE_PKG = "j2py.wire"
CONTRACT_MODULE = "j2py.wiring_contract"
PLUGINS_PKG = "j2py.framework_plugins"


def _module_name(path: Path) -> str:
    rel = path.relative_to(REPO_ROOT).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _imported_j2py_targets(path: Path) -> set[str]:
    """Absolute ``j2py.*`` modules imported by ``path`` (relative imports skipped)."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "j2py" or alias.name.startswith("j2py."):
                    targets.add(alias.name)
        elif (
            isinstance(node, ast.ImportFrom)
            and node.level == 0
            and node.module
            and (node.module == "j2py" or node.module.startswith("j2py."))
        ):
            targets.add(node.module)
    return targets


def _is_wire(target: str) -> bool:
    # NB: the trailing dot matters -- ``j2py.wiring_contract`` must NOT count as wire.
    return target == WIRE_PKG or target.startswith(WIRE_PKG + ".")


def _is_plugin(target: str) -> bool:
    return target == PLUGINS_PKG or target.startswith(PLUGINS_PKG + ".")


def _python_files() -> list[Path]:
    return sorted(PKG_ROOT.rglob("*.py"))


def test_core_does_not_import_wire() -> None:
    offenders: list[str] = []
    for path in _python_files():
        module = _module_name(path)
        if _is_wire(module) or module == CONTRACT_MODULE:
            continue  # the consumer and the shared facade are not "core" here
        for target in sorted(_imported_j2py_targets(path)):
            if _is_wire(target):
                offenders.append(f"{module} -> {target}")
    assert not offenders, (
        "core modules must not import the j2py.wire consumer (arrow is consumer -> core):\n"
        + "\n".join(offenders)
    )


def test_wire_consumer_touches_core_only_through_contract() -> None:
    offenders: list[str] = []
    for path in _python_files():
        module = _module_name(path)
        if not _is_wire(module):
            continue
        for target in sorted(_imported_j2py_targets(path)):
            allowed = _is_wire(target) or target == CONTRACT_MODULE
            if not allowed:
                offenders.append(f"{module} -> {target}")
    assert not offenders, (
        "j2py.wire may import core only via "
        f"{CONTRACT_MODULE!r} (not Internal j2py.pipeline / j2py.translate.* surfaces):\n"
        + "\n".join(offenders)
    )


def test_core_does_not_import_framework_plugins() -> None:
    offenders: list[str] = []
    for path in _python_files():
        module = _module_name(path)
        if _is_plugin(module):
            continue  # plugins may import sibling plugin modules; they are not "core"
        for target in sorted(_imported_j2py_targets(path)):
            if _is_plugin(target):
                offenders.append(f"{module} -> {target}")
    assert not offenders, (
        "core must stay framework-neutral: nothing outside j2py.framework_plugins may "
        "import a producer plugin (plugins are config-injected; the arrow is plugin -> "
        "core, never core -> plugin):\n" + "\n".join(offenders)
    )


def test_contract_facade_does_not_import_wire() -> None:
    # The facade is owned by core; it must not depend on the consumer it serves.
    facade = PKG_ROOT / "wiring_contract.py"
    assert facade.exists(), "expected j2py/wiring_contract.py facade to exist"
    offenders = sorted(t for t in _imported_j2py_targets(facade) if _is_wire(t))
    assert not offenders, f"wiring_contract facade must not import j2py.wire: {offenders}"
