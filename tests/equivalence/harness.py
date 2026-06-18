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

import decimal
import math
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
    if injected_globals:
        module.__dict__.update(injected_globals)
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


class JavaBoolean:
    """Small Java-style ``Boolean`` shim for equivalence fixtures."""

    def __init__(self, value: Any) -> None:
        self.value = bool(value)

    @classmethod
    def value_of(cls, value: Any) -> JavaBoolean:
        return JavaBoolean(value)

    def boolean_value(self) -> bool:
        return self.value

    def __bool__(self) -> bool:
        return self.value

    def __eq__(self, other: object) -> bool:
        if isinstance(other, JavaBoolean):
            return self.value == other.value
        if isinstance(other, bool):
            return self.value == other
        return False

    def __repr__(self) -> str:
        return "TRUE" if self.value else "FALSE"


JavaBoolean.TRUE = JavaBoolean(True)  # type: ignore[attr-defined]
JavaBoolean.FALSE = JavaBoolean(False)  # type: ignore[attr-defined]


class BigDecimal(decimal.Decimal):
    """Small Java-style ``BigDecimal`` shim for equivalence fixtures."""

    def __new__(cls, value: Any = "0", context: decimal.Context | None = None) -> BigDecimal:
        try:
            return super().__new__(cls, value, context=context)
        except decimal.InvalidOperation as exc:
            raise ValueError(value) from exc

    @classmethod
    def value_of(cls, value: Any) -> BigDecimal:
        return cls(str(value))

    def double_value(self) -> float:
        return float(self)

    def set_scale(self, scale: int, rounding_mode: str | None = None) -> BigDecimal:
        quantizer = decimal.Decimal(1).scaleb(-scale)
        if rounding_mode == "UNNECESSARY":
            result = self.quantize(quantizer, rounding=decimal.ROUND_DOWN)
            if result != self:
                raise ArithmeticError("Rounding necessary")
            return BigDecimal(result)
        rounding = rounding_mode or decimal.ROUND_HALF_EVEN
        return BigDecimal(self.quantize(quantizer, rounding=rounding))


BigDecimal.ZERO = BigDecimal("0")  # type: ignore[attr-defined]


class JavaDouble(float):
    """Small Java-style ``Double`` shim for equivalence fixtures."""

    @classmethod
    def value_of(cls, value: Any) -> JavaDouble:
        return cls(float(value))

    def double_value(self) -> float:
        return float(self)

    def is_infinite(self) -> bool:
        return math.isinf(self)


class JavaFloat(float):
    """Small Java-style ``Float`` shim for equivalence fixtures."""

    @classmethod
    def value_of(cls, value: Any) -> JavaFloat:
        return cls(float(value))

    @classmethod
    def parse_float(cls, value: Any) -> JavaFloat:
        return cls.value_of(value)

    def float_value(self) -> float:
        return float(self)

    def is_infinite(self) -> bool:
        return math.isinf(self)


class RoundingMode:
    """Java ``RoundingMode`` constants mapped to ``decimal`` rounding modes."""

    UP = decimal.ROUND_UP
    DOWN = decimal.ROUND_DOWN
    CEILING = decimal.ROUND_CEILING
    FLOOR = decimal.ROUND_FLOOR
    HALF_UP = decimal.ROUND_HALF_UP
    HALF_DOWN = decimal.ROUND_HALF_DOWN
    HALF_EVEN = decimal.ROUND_HALF_EVEN
    UNNECESSARY = "UNNECESSARY"


def number_utils_runtime_globals() -> dict[str, Any]:
    """Runtime globals needed by generated NumberUtils BigDecimal methods."""
    return {
        "BigDecimal": BigDecimal,
        "Decimal": BigDecimal,
        "INTEGER_TWO": 2,
    }


def install_java_lang_stubs() -> list[str]:
    """Install stub module chains needed to load the NumberUtils fixture.

    At class-body definition time NumberUtils calls::

        Long.value_of(0), Short.value_of(...), Byte.value_of(...),
        Double.value_of(0.0), Float.value_of(0.0), Integer.MIN_VALUE, Integer.MAX_VALUE,
        and BigDecimal/RoundingMode helpers

    — all imported from ``org.apache.commons.lang3.math.*`` (the rule layer maps Java
    boxed types to sibling fqns).  Method bodies also reference ``StringUtils.contains``,
    ``Validate.is_true``, ``Float.parse_float``, ``Byte.parse_byte``, ``Short.parse_short``,
    and ``java.lang.reflect.Array``.

    Most stubs are identity functions or no-ops — they make the module importable and
    class-body initializers runnable.  Primitive parsers enforce Java range limits so
    NumberUtils fallback behavior is tested against the Java contract.

    Returns the list of module names newly added to ``sys.modules``; pass (reversed) to
    teardown for precise cleanup.
    """
    _id: Any = lambda x: x  # noqa: E731

    def _parse_ranged_int(value: Any, min_value: int, max_value: int) -> int:
        parsed = int(value)
        if parsed < min_value or parsed > max_value:
            raise ValueError(value)
        return parsed

    def _parse_short(value: Any) -> int:
        return _parse_ranged_int(value, -(2**15), 2**15 - 1)

    def _parse_byte(value: Any) -> int:
        return _parse_ranged_int(value, -(2**7), 2**7 - 1)

    def _decode_integer(value: Any) -> int:
        text = str(value)
        if text != text.strip():
            raise ValueError(value)
        sign = -1 if text.startswith("-") else 1
        unsigned = text[1:] if text[:1] in {"+", "-"} else text
        if unsigned.startswith(("0x", "0X")):
            parsed = int(unsigned[2:], 16)
        elif unsigned.startswith("#"):
            parsed = int(unsigned[1:], 16)
        elif len(unsigned) > 1 and unsigned.startswith("0"):
            parsed = int(unsigned[1:], 8)
        else:
            parsed = int(unsigned, 10)
        return sign * parsed

    math = "org.apache.commons.lang3.math"
    lang3 = "org.apache.commons.lang3"

    installed: list[str] = []
    installed += install_stub_class(
        f"{math}.Long",
        "Long",
        types.SimpleNamespace(value_of=_id, decode=_decode_integer),
    )
    installed += install_stub_class(
        f"{math}.Short",
        "Short",
        types.SimpleNamespace(value_of=_id, parse_short=_parse_short),
    )
    installed += install_stub_class(
        f"{math}.Byte",
        "Byte",
        types.SimpleNamespace(value_of=_id, parse_byte=_parse_byte),
    )
    installed += install_stub_class(
        f"{math}.Double",
        "Double",
        types.SimpleNamespace(
            value_of=JavaDouble.value_of,
            is_na_n=lambda value: value != value,
            na_n=float("nan"),
        ),
    )
    installed += install_stub_class(
        f"{math}.Float",
        "Float",
        types.SimpleNamespace(
            value_of=JavaFloat.value_of,
            parse_float=JavaFloat.parse_float,
            is_na_n=lambda value: value != value,
            na_n=float("nan"),
        ),
    )
    installed += install_stub_class(
        f"{math}.Integer",
        "Integer",
        types.SimpleNamespace(
            value_of=_id,
            decode=_decode_integer,
            MIN_VALUE=-(2**31),
            MAX_VALUE=2**31 - 1,
        ),
    )
    installed += install_stub_class(
        f"{math}.Character", "Character", types.SimpleNamespace(value_of=_id)
    )
    installed += install_stub_class("java.math.BigDecimal", "BigDecimal", BigDecimal)
    installed += install_stub_class(
        f"{lang3}.StringUtils",
        "StringUtils",
        types.SimpleNamespace(
            contains=lambda s, sub: (sub in s) if s is not None else False,
            is_blank=lambda s: s is None or str(s).strip() == "",
            is_empty=lambda s: s is None or s == "",
            is_numeric=lambda s: s is not None and str(s).isdecimal(),
        ),
    )
    installed += install_stub_class(
        f"{lang3}.Validate",
        "Validate",
        types.SimpleNamespace(is_true=lambda *_: None, not_empty=lambda value, *_: value),
    )
    installed += install_stub_class(
        "java.lang.reflect.Array",
        "Array",
        types.SimpleNamespace(get_length=len),
    )
    installed += install_stub_class(
        "java.math.RoundingMode",
        "RoundingMode",
        RoundingMode,
    )
    return installed


# ---------------------------------------------------------------------------
# BooleanUtils stubs
# ---------------------------------------------------------------------------


def boolean_utils_stub() -> types.SimpleNamespace:
    """Stub for Commons-Lang ``Boolean`` used by the BooleanUtils fixture."""

    return types.SimpleNamespace(
        TRUE=JavaBoolean.TRUE,
        FALSE=JavaBoolean.FALSE,
        value_of=JavaBoolean.value_of,
    )


def install_boolean_utils_stubs() -> list[str]:
    """Install minimal module chains needed to load the BooleanUtils fixture."""
    installed: list[str] = []
    installed += install_stub_class(
        "org.apache.commons.lang3.Boolean",
        "Boolean",
        boolean_utils_stub(),
    )
    installed += install_stub_class(
        "org.apache.commons.lang3.math.NumberUtils",
        "NumberUtils",
        types.SimpleNamespace(INTEGER_ONE=1, INTEGER_ZERO=0),
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
        return str(seq).find(str(search_seq), max(0, start))

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
        s_seq = str(seq)
        s_sub = str(substring)
        if this_start > len(s_seq) or start > len(s_sub):
            return False
        left = s_seq[this_start : this_start + length]
        right = s_sub[start : start + length]
        if len(left) != length or len(right) != length:
            return False
        if ignore_case:
            return left.casefold() == right.casefold()
        return left == right

    return types.SimpleNamespace(index_of=index_of, region_matches=region_matches)


def character_stub() -> types.SimpleNamespace:
    """Stub for Java ``Character`` methods used by StringUtils."""

    def is_whitespace(ch: Any) -> bool:
        return chr(ch).isspace() if isinstance(ch, int) else str(ch).isspace()

    return types.SimpleNamespace(is_whitespace=is_whitespace)


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


# ---------------------------------------------------------------------------
# Guava Strings stubs
# ---------------------------------------------------------------------------


class JavaString:
    """Small Java-style ``String`` shim for generated Guava Strings methods."""

    def __init__(self, value: Any) -> None:
        self.value = str(value)

    def __len__(self) -> int:
        return len(self.value)

    def __str__(self) -> str:
        return self.value

    def __eq__(self, other: object) -> bool:
        if other is None:
            return False
        if isinstance(other, JavaString):
            return self.value == other.value
        return self.value == str(other)

    def get_chars(self, start: int, end: int, target: list[str], target_start: int) -> None:
        for offset, char in enumerate(self.value[start:end]):
            target[target_start + offset] = char


class JavaCharSequence:
    """Small Java-style ``CharSequence`` shim with ``subSequence`` support."""

    def __init__(self, value: Any) -> None:
        self.value = str(value)

    def __len__(self) -> int:
        return len(self.value)

    def __getitem__(self, index: int) -> str:
        return self.value[index]

    def __str__(self) -> str:
        return self.value

    def sub_sequence(self, start: int, end: int) -> JavaCharSequence:
        return JavaCharSequence(self.value[start:end])


class GuavaStringBuilder:
    """Subset of ``StringBuilder`` used by generated Guava Strings code."""

    def __init__(self, _capacity: int = 0) -> None:
        self._parts: list[str] = []

    def append(
        self, value: Any, start: int | None = None, end: int | None = None
    ) -> GuavaStringBuilder:
        text = "null" if value is None else str(value)
        self._parts.append(text if start is None or end is None else text[start:end])
        return self

    def __str__(self) -> str:
        return "".join(self._parts)


def guava_strings_platform_stub() -> types.SimpleNamespace:
    """Stub for Guava ``Platform`` methods delegated to by ``Strings``."""

    return types.SimpleNamespace(
        null_to_empty=lambda value: "" if value is None else value,
        empty_to_null=lambda value: None if value is None or value == "" else value,
        string_is_null_or_empty=lambda value: value is None or value == "",
    )


def guava_strings_character_stub() -> types.SimpleNamespace:
    """Stub for Java surrogate-pair helpers used by generated ``Strings``."""

    def is_high_surrogate(ch: str) -> bool:
        return 0xD800 <= ord(ch) <= 0xDBFF

    def is_low_surrogate(ch: str) -> bool:
        return 0xDC00 <= ord(ch) <= 0xDFFF

    return types.SimpleNamespace(
        is_high_surrogate=is_high_surrogate,
        is_low_surrogate=is_low_surrogate,
    )


def install_guava_strings_stubs() -> list[str]:
    """Install minimal module chains needed to load the Guava Strings fixture."""

    def arraycopy(
        source: list[str], source_pos: int, dest: list[str], dest_pos: int, length: int
    ) -> None:
        dest[dest_pos : dest_pos + length] = source[source_pos : source_pos + length]

    installed: list[str] = []
    installed += install_stub_class(
        "java.util.logging.Logger",
        "Logger",
        types.SimpleNamespace(get_logger=lambda *_: types.SimpleNamespace(log=lambda *_: None)),
    )
    installed += install_stub_class(
        "com.google.common.base.Platform",
        "Platform",
        guava_strings_platform_stub(),
    )
    installed += install_stub_class(
        "com.google.common.base.StringBuilder",
        "StringBuilder",
        GuavaStringBuilder,
    )
    installed += install_stub_class(
        "com.google.common.base.Character",
        "Character",
        guava_strings_character_stub(),
    )
    installed += install_stub_class(
        "com.google.common.base.String",
        "String",
        lambda chars: "".join(chars),
    )
    installed += install_stub_class(
        "com.google.common.base.System",
        "System",
        types.SimpleNamespace(
            arraycopy=arraycopy,
            identity_hash_code=id,
        ),
    )
    return installed


_FIXTURE_STUB_INSTALLERS = {
    "BooleanUtils.java": install_boolean_utils_stubs,
    "CharUtils.java": install_array_utils_stub_package,
    "Strings.java": install_guava_strings_stubs,
    "NumberUtils.java": install_java_lang_stubs,
    "StringUtils.java": install_string_utils_stubs,
}


def install_fixture_stubs(java_name: str) -> list[str]:
    """Install dependency stubs needed to load a translated equivalence fixture."""
    installer = _FIXTURE_STUB_INSTALLERS.get(java_name)
    if installer is None:
        return []
    return installer()
