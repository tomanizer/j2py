"""Phase 1 equivalence harness (see docs/EQUIVALENCE_TESTING.md).

Translate a vendored Java fixture rule-layer-only, load the result as an in-memory
module, and let literal-oracle assertions ported from the upstream unit tests run
against it. Java-derived literals are the oracle (JVM-independent), so a failing
assertion is a transpiler divergence — not a fixture artefact.

The harness translates at test time (not from a frozen Python snapshot) so that when a
translation bug is fixed the corresponding ``xfail(strict)`` flips and forces its own
removal, mirroring the behaviour-corpus discipline.
"""

from __future__ import annotations

import sys
import types
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from j2py.config.loader import ConfigLoader
from j2py.pipeline import translate_file

FIXTURES = Path(__file__).parent.parent / "fixtures" / "equivalence"

# Production config — the same invocation the CLI and behaviour corpus use.
_CFG = ConfigLoader().add_defaults().build()


def translate_rule_layer(java_name: str) -> str:
    """Return the rule-layer-only Python translation of a vendored Java fixture."""
    result = translate_file(FIXTURES / java_name, cfg=_CFG, use_llm=False, validate=False)
    return result.python_source


def load_translated_module(
    source: str, name: str, injected_globals: Mapping[str, Any] | None = None
) -> types.ModuleType:
    """Execute translated Python source as a module.

    ``injected_globals`` supplies stubs for unresolved cross-class dependencies that the
    translation references but does not import — the dependency-closure obstacle
    documented in EQUIVALENCE_TESTING §8. Stubs are NOT under test; they only make the
    class importable so its own methods can be exercised.
    """
    module = types.ModuleType(name)
    module.__file__ = f"<{name}>"
    sys.modules[name] = module
    if injected_globals:
        module.__dict__.update(injected_globals)
    exec(compile(source, f"<{name}>", "exec"), module.__dict__)  # noqa: S102
    return module


def array_utils_stub() -> types.SimpleNamespace:
    """Stub for Commons-Lang ``ArrayUtils`` (only ``setAll`` is referenced by CharUtils).

    The translation imports this as ``ArrayUtils`` and calls ``ArrayUtils.set_all``.
    """

    def set_all(array: list[Any], generator: Any) -> list[Any]:
        for i in range(len(array)):
            array[i] = generator(i)
        return array

    return types.SimpleNamespace(set_all=set_all)


def install_array_utils_stub_package() -> list[str]:
    """Install a minimal module chain for ``org.apache.commons.lang3.ArrayUtils``."""
    module_names = [
        "org",
        "org.apache",
        "org.apache.commons",
        "org.apache.commons.lang3",
        "org.apache.commons.lang3.ArrayUtils",
    ]
    for name in module_names:
        module = types.ModuleType(name)
        if name != module_names[-1]:
            module.__path__ = []  # type: ignore[attr-defined]
        sys.modules[name] = module

    for parent_name, child_name in zip(module_names, module_names[1:], strict=False):
        parent = sys.modules[parent_name]
        child = sys.modules[child_name]
        setattr(parent, child_name.rsplit(".", 1)[-1], child)

    sys.modules[module_names[-1]].ArrayUtils = array_utils_stub()  # type: ignore[attr-defined]
    return module_names
