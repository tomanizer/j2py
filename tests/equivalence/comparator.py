"""Equivalence comparator — the written spec for Java↔Python behavioural equivalence.

This module is the **trust anchor** for the equivalence gate (see
``docs/EQUIVALENCE_TESTING.md`` §2 and §6).  Every normalisation decision is encoded
here as executable code; tests should use the helpers rather than bare ``==`` so that
rule changes propagate automatically.

Normalisation rules
-------------------

**1. Integer width / overflow**
  Java ``int`` is 32-bit signed (−2³¹ … 2³¹−1); Java ``long`` is 64-bit signed.
  Python ``int`` is unbounded.  Two positions are possible:

    a. Model Java overflow — wrap every result to Java width.
    b. Treat overflow as a translation bug — in-range inputs must produce equal values;
       overflow inputs are excluded from literal-oracle tests (the oracle itself overflows).

  Phase 1 adopts position (b): literal-oracle assertions use only in-range values, so no
  wrapping is needed in comparisons.  ``java_int`` / ``java_long`` are provided for
  boundary-value constants in test expressions (e.g. ``INT_MIN``), not for wrapping
  results.  If a translated method overflows for an in-range input that is a Phase 1 bug.

**2. Float approximation**
  Java ``float`` is IEEE 754 single-precision (~7 significant digits).
  Java ``double`` is double-precision (~15 significant digits).
  Python ``float`` is always double-precision.  Use ``approx_float`` for Java-``float``
  results (``rel=1e-5``) and ``approx_double`` for Java-``double`` results (``rel=1e-9``).

**3. null / None**
  Java ``null`` maps to Python ``None``.  Methods that return ``null`` on error should
  return ``None``.  ``to_*`` helpers return a caller-supplied default instead — tested
  with the literal default value directly.

**4. Boolean identity**
  Python ``bool`` is a subtype of ``int``; ``True is True`` and ``False is False`` hold.
  Predicate methods return Python ``bool``; ``is True`` / ``is False`` assertions are
  correct and preferred over ``== True`` / ``== False``.

**5. Exception mapping**
  Java exceptions map to Python exceptions via ``EXCEPTION_MAP`` in
  ``j2py/config/default.py``.  ``assert_raises_mapped`` enforces the runtime mapping
  for methods that raise on invalid input.
"""

from __future__ import annotations

import builtins
import contextlib
import functools
from collections.abc import Iterator
from typing import Any, cast

import pytest

# ---------------------------------------------------------------------------
# Integer range constants
# ---------------------------------------------------------------------------

INT_MIN: int = -(2**31)  # Java Integer.MIN_VALUE
INT_MAX: int = 2**31 - 1  # Java Integer.MAX_VALUE
LONG_MIN: int = -(2**63)  # Java Long.MIN_VALUE
LONG_MAX: int = 2**63 - 1  # Java Long.MAX_VALUE
BYTE_MIN: int = -(2**7)  # Java Byte.MIN_VALUE
BYTE_MAX: int = 2**7 - 1  # Java Byte.MAX_VALUE
SHORT_MIN: int = -(2**15)  # Java Short.MIN_VALUE
SHORT_MAX: int = 2**15 - 1  # Java Short.MAX_VALUE


# ---------------------------------------------------------------------------
# Integer helpers (position b — boundary values only, not wrapping)
# ---------------------------------------------------------------------------


def java_int(n: int) -> int:
    """Wrap ``n`` to Java ``int`` range (32-bit signed).

    Use only for expressing boundary-value constants in test assertions, not for
    wrapping method results.  Wrapping a method result masks overflow bugs.
    """
    n = n & 0xFFFFFFFF
    return n if n < 0x80000000 else n - 0x100000000


def java_long(n: int) -> int:
    """Wrap ``n`` to Java ``long`` range (64-bit signed)."""
    n = n & 0xFFFFFFFFFFFFFFFF
    return n if n < 0x8000000000000000 else n - 0x10000000000000000


# ---------------------------------------------------------------------------
# Float helpers
# ---------------------------------------------------------------------------


def approx_float(value: float, rel: float = 1e-5) -> Any:
    """``pytest.approx`` at single-precision tolerance for Java ``float`` results."""
    return pytest.approx(value, rel=rel)


def approx_double(value: float, rel: float = 1e-9) -> Any:
    """``pytest.approx`` at double-precision tolerance for Java ``double`` results."""
    return pytest.approx(value, rel=rel)


# ---------------------------------------------------------------------------
# Exception mapping helper
# ---------------------------------------------------------------------------


@functools.lru_cache(maxsize=1)
def _get_exception_map() -> dict[str, str]:
    from j2py.config.loader import ConfigLoader

    return ConfigLoader().add_defaults().build().exception_map


@contextlib.contextmanager
def assert_raises_mapped(java_exception: str) -> Iterator[pytest.ExceptionInfo[Exception]]:
    """Assert that the block raises the Python exception mapped from ``java_exception``.

    Uses the same ``EXCEPTION_MAP`` as the translator so that if the map changes,
    both the translation and the test expectation update together.

    Example::

        with assert_raises_mapped("NumberFormatException"):
            NumberUtils.create_integer("not-a-number")
    """
    py_exc_name = _get_exception_map().get(java_exception)
    if py_exc_name is None:
        raise KeyError(
            f"{java_exception!r} not in EXCEPTION_MAP — add it or use pytest.raises directly"
        )
    py_exc_obj = getattr(builtins, py_exc_name, None)
    if py_exc_obj is None:
        raise AttributeError(f"Python exception class {py_exc_name!r} not found in builtins")
    if not isinstance(py_exc_obj, type) or not issubclass(py_exc_obj, Exception):
        raise TypeError(f"Python exception class {py_exc_name!r} is not an Exception subclass")
    py_exc = cast(type[Exception], py_exc_obj)
    with pytest.raises(py_exc) as exc_info:
        yield exc_info
