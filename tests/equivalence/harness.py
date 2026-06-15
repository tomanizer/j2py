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

import j2py.translate.runtime.j2py_runtime as _j2py_runtime_module
from j2py.config.loader import ConfigLoader
from j2py.pipeline import translate_file

# Translated files always emit `from j2py_runtime import overloaded`.
# Register the module under its expected top-level name so exec() can find it.
sys.modules.setdefault("j2py_runtime", _j2py_runtime_module)

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


# ---------------------------------------------------------------------------
# Generic stub installer
# ---------------------------------------------------------------------------


def _install_module_chain(fqn: str) -> list[str]:
    """Create module objects for every prefix of ``fqn`` and register in sys.modules.

    Only modules not already present are created; pre-existing entries are left
    untouched.  Returns the names of modules *newly* added so callers can undo
    registration precisely without clobbering unrelated entries.
    """
    parts = fqn.split(".")
    names = [".".join(parts[: i + 1]) for i in range(len(parts))]
    newly_installed: list[str] = []
    for name in names:
        if name not in sys.modules:
            module = types.ModuleType(name)
            if name != names[-1]:  # non-leaf is a package
                module.__path__ = []
            sys.modules[name] = module
            newly_installed.append(name)
    # Wire parent.__child__ attributes (only if not already set).
    for parent_name, child_name in zip(names, names[1:], strict=False):
        parent = sys.modules[parent_name]
        attr = child_name.rsplit(".", 1)[-1]
        if not hasattr(parent, attr):
            setattr(parent, attr, sys.modules[child_name])
    return newly_installed


def install_stub_class(module_fqn: str, class_name: str, stub: object) -> list[str]:
    """Register a stub object as ``class_name`` on a synthetic module at ``module_fqn``.

    Creates the full dotted module chain for ``module_fqn`` if not already present.
    Returns the list of module names *newly* added to ``sys.modules``; pass the list
    (reversed) to teardown so cleanup is precise and doesn't remove pre-existing entries.

    Example::

        install_stub_class(
            "org.apache.commons.lang3.math.Long",
            "Long",
            types.SimpleNamespace(value_of=lambda x: x),
        )
    """
    installed = _install_module_chain(module_fqn)
    setattr(sys.modules[module_fqn], class_name, stub)
    return installed


# ---------------------------------------------------------------------------
# ArrayUtils stub (CharUtils dependency)
# ---------------------------------------------------------------------------


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
    return install_stub_class(
        "org.apache.commons.lang3.ArrayUtils",
        "ArrayUtils",
        array_utils_stub(),
    )


# ---------------------------------------------------------------------------
# Java boxed-type stubs (NumberUtils dependency)
# ---------------------------------------------------------------------------


def install_java_lang_stubs() -> list[str]:
    """Install stub module chains needed to load the NumberUtils fixture.

    At class-body definition time NumberUtils calls::

        Long.value_of(0), Short.value_of(...), Byte.value_of(...),
        Double.value_of(0.0), Float.value_of(0.0), Integer.min_value

    — all imported from ``org.apache.commons.lang3.math.*`` (the rule layer maps Java
    boxed types to sibling fqns).  Method bodies also reference ``StringUtils.contains``,
    ``Validate.is_true``, ``Float.parse_float``, ``Byte.parse_byte``, ``Short.parse_short``,
    and ``java.lang.reflect.Array``.

    All stubs are identity functions or no-ops — they make the module importable and
    class-body initializers runnable.  They are NOT under test.

    Returns the list of module names newly added to ``sys.modules``; pass (reversed) to
    teardown for precise cleanup.
    """
    _id: Any = lambda x: x  # noqa: E731

    math = "org.apache.commons.lang3.math"
    lang3 = "org.apache.commons.lang3"

    installed: list[str] = []
    installed += install_stub_class(
        f"{math}.Long", "Long", types.SimpleNamespace(value_of=_id)
    )
    installed += install_stub_class(
        f"{math}.Short", "Short",
        types.SimpleNamespace(value_of=_id, parse_short=int),
    )
    installed += install_stub_class(
        f"{math}.Byte", "Byte",
        types.SimpleNamespace(value_of=_id, parse_byte=int),
    )
    installed += install_stub_class(
        f"{math}.Double", "Double", types.SimpleNamespace(value_of=_id)
    )
    installed += install_stub_class(
        f"{math}.Float", "Float",
        types.SimpleNamespace(value_of=_id, parse_float=float),
    )
    installed += install_stub_class(
        f"{math}.Integer", "Integer",
        types.SimpleNamespace(
            value_of=_id,
            min_value=-(2**31),
            max_value=2**31 - 1,
        ),
    )
    installed += install_stub_class(
        f"{math}.Character", "Character", types.SimpleNamespace(value_of=_id)
    )
    installed += install_stub_class(
        f"{lang3}.StringUtils", "StringUtils",
        types.SimpleNamespace(
            contains=lambda s, sub: (sub in s) if s is not None else False,
        ),
    )
    installed += install_stub_class(
        f"{lang3}.Validate", "Validate",
        types.SimpleNamespace(is_true=lambda *_: None),
    )
    installed += install_stub_class(
        "java.lang.reflect.Array", "Array", types.SimpleNamespace()
    )
    return installed


# ---------------------------------------------------------------------------
# StringUtils stubs
# ---------------------------------------------------------------------------


def char_sequence_utils_stub() -> types.SimpleNamespace:
    """Stub for Commons-Lang ``CharSequenceUtils`` methods used by StringUtils.

    The translated fixture imports this as ``CharSequenceUtils`` and calls
    ``index_of`` / ``region_matches``. The implementations use Python string
    semantics for literal-oracle cases; the stub itself is not under test.
    """

    def index_of(seq: Any, search_seq: Any, start: int) -> int:
        return str(seq).find(str(search_seq), start)

    def region_matches(
        seq: Any,
        ignore_case: bool,
        this_start: int,
        substring: Any,
        start: int,
        length: int,
    ) -> bool:
        if this_start < 0 or start < 0 or length < 0:
            return False
        left = str(seq)[this_start : this_start + length]
        right = str(substring)[start : start + length]
        if len(left) != length or len(right) != length:
            return False
        if ignore_case:
            return left.casefold() == right.casefold()
        return left == right

    return types.SimpleNamespace(index_of=index_of, region_matches=region_matches)


def character_stub() -> types.SimpleNamespace:
    """Stub for Java ``Character`` methods used by StringUtils."""

    return types.SimpleNamespace(is_whitespace=lambda ch: str(ch).isspace())


def install_string_utils_stubs() -> list[str]:
    """Install minimal module chains needed to load the StringUtils fixture."""
    installed: list[str] = []
    installed += install_stub_class(
        "org.apache.commons.lang3.CharSequenceUtils",
        "CharSequenceUtils",
        char_sequence_utils_stub(),
    )
    installed += install_stub_class(
        "org.apache.commons.lang3.Character",
        "Character",
        character_stub(),
    )
    return installed
