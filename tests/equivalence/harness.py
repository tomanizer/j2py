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
    result = translate_file(
        FIXTURES / java_name, cfg=_CFG, use_llm=False, validate=False
    )
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

    The translation emits ``array_utils.set_all(arr, fn)`` — see bug #188 — so the stub is
    injected under the name ``array_utils``.
    """

    def set_all(array: list[Any], generator: Any) -> list[Any]:
        for i in range(len(array)):
            array[i] = generator(i)
        return array

    return types.SimpleNamespace(set_all=set_all)
