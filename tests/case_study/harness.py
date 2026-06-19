"""End-to-end case-study harness for the commons-lang ``tuple`` package (issue #311).

Translates the six vendored ``org.apache.commons.lang3.tuple`` Java files with the rule
layer only (no LLM), then *links* the translated modules into one shared namespace so
the real translated classes can be exercised by ported unit tests.

Why a link step rather than plain ``import``: the package is a cross-referential class
hierarchy — ``Pair`` delegates to ``ImmutablePair`` (a factory call) while
``ImmutablePair`` ``extends Pair``. With eager Python ``from X import Y`` imports this is
a circular import (tracked as a translator limitation; see docs/CASE_STUDY_COMMONS_LANG_TUPLE.md). Linking
the package into a single namespace, in dependency order, exercises the translated class
bodies and methods without that cross-module cycle — analogous to how
``tests/equivalence/harness.py`` injects dependency stubs that are "not under test".

External, non-translated dependencies (``java.util.Objects``, ``Map.Entry``,
``CompareToBuilder``) are supplied as small stubs. They are scaffolding, not under test:
the oracle is the translated tuple logic itself.
"""

from __future__ import annotations

import abc
import sys
import types
from pathlib import Path
from typing import Any

import j2py.translate.runtime.j2py_runtime as _j2py_runtime_module
from j2py.config.loader import ConfigLoader
from j2py.pipeline import translate_file

# Translated files emit ``from j2py_runtime import overloaded``; register the module
# under the expected top-level name so the linked exec() can resolve it.
sys.modules.setdefault("j2py_runtime", _j2py_runtime_module)

JAVA_DIR = Path(__file__).parent.parent / "fixtures" / "case_study" / "commons_lang_tuple" / "java"

_CFG = ConfigLoader().add_defaults().build()

# Dependency order: abstract bases first, then concrete subclasses.
_LINK_ORDER = (
    "Pair",
    "Triple",
    "ImmutablePair",
    "MutablePair",
    "ImmutableTriple",
    "MutableTriple",
)


def translate_tuple_package() -> dict[str, str]:
    """Return ``{class_name: translated_python_source}`` for the six tuple files."""
    sources: dict[str, str] = {}
    for name in _LINK_ORDER:
        result = translate_file(JAVA_DIR / f"{name}.java", cfg=_CFG, use_llm=False, validate=False)
        sources[name] = result.python_source
    return sources


def _objects_stub() -> types.SimpleNamespace:
    """Minimal ``java.util.Objects`` (only ``hashCode`` is referenced)."""

    def hash_code(value: Any) -> int:
        return 0 if value is None else hash(value)

    return types.SimpleNamespace(hash_code=hash_code)


def _map_stub() -> types.SimpleNamespace:
    """``Map.Entry`` marker used in ``isinstance`` checks and type positions.

    The translated ``Pair`` inherits ``Map.Entry`` semantics; the real classes register
    themselves against this base so ``isinstance(pair, Map.Entry)`` holds.
    """

    class Entry(abc.ABC):  # noqa: B024 - ABCMeta marker for register()/isinstance only
        # ``Map.Entry[Any, Any]`` appears in a runtime ``cast(...)`` in the translated
        # equals(); make the marker subscriptable like a typing generic.
        def __class_getitem__(cls, _params: Any) -> type:
            return cls

    return types.SimpleNamespace(Entry=Entry)


class _CompareToBuilder:
    """Minimal Commons-Lang ``CompareToBuilder`` (lexicographic field comparison)."""

    def __init__(self) -> None:
        self._result = 0

    def append(self, left: Any, right: Any) -> _CompareToBuilder:
        if self._result != 0:
            return self
        if left == right:
            self._result = 0
        elif left is None:
            self._result = -1
        elif right is None:
            self._result = 1
        elif left < right:
            self._result = -1
        else:
            self._result = 1
        return self

    def to_comparison(self) -> int:
        return self._result


def link_tuple_namespace() -> types.SimpleNamespace:
    """Translate and link the tuple package, returning the exercised classes.

    The returned namespace exposes ``Pair``, ``ImmutablePair``, ``MutablePair``,
    ``Triple``, ``ImmutableTriple``, ``MutableTriple`` and the ``Map`` stub.
    """
    sources = translate_tuple_package()
    map_stub = _map_stub()
    shared: dict[str, Any] = {
        "Objects": _objects_stub(),
        "Map": map_stub,
        "CompareToBuilder": _CompareToBuilder,
    }

    for name in _LINK_ORDER:
        linked = _strip_linked_imports(sources[name])
        exec(compile(linked, f"<case_study:{name}>", "exec"), shared)  # noqa: S102

    # The translated Pair implements Map.Entry; register it as a virtual subclass so
    # isinstance(pair, Map.Entry) checks in equals() resolve true.
    map_stub.Entry.register(shared["Pair"])

    return types.SimpleNamespace(**{name: shared[name] for name in _LINK_ORDER}, Map=map_stub)


def _strip_linked_imports(source: str) -> str:
    """Drop imports resolved by the shared namespace, keep genuine library imports.

    Removed: intra-package ``from org.apache.commons.lang3.tuple.X import X`` (all six
    classes share one linked namespace) and ``from java...`` stdlib imports (supplied as
    stubs in the namespace). Kept: ``__future__``, ``j2py_runtime``, ``abc``, ``typing``.
    """
    kept: list[str] = []
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("from org.apache.commons.lang3.tuple."):
            continue
        if stripped.startswith(("from java.", "import java.")):
            continue
        kept.append(line)
    return "\n".join(kept)
