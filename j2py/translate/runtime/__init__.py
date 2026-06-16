"""Vendored runtime support emitted next to translated Python output.

``j2py_runtime.py`` is self-contained (stdlib only) so the pipeline can copy
its source verbatim into the output tree. See ADR 0009.
"""

from __future__ import annotations

from pathlib import Path

from j2py.translate.runtime.j2py_runtime import (
    Comparator,
    MalformedObjectNameException,
    ObjectName,
    __j2py_todo__,
    _j2py_idiv,
    _j2py_monitor,
    overloaded,
)

RUNTIME_MODULE_NAME = "j2py_runtime"
RUNTIME_IMPORT_LINE = f"from {RUNTIME_MODULE_NAME} import overloaded"
RUNTIME_IDIV_IMPORT_LINE = f"from {RUNTIME_MODULE_NAME} import _j2py_idiv"
RUNTIME_TODO_IMPORT_LINE = f"from {RUNTIME_MODULE_NAME} import __j2py_todo__"
RUNTIME_MONITOR_IMPORT_LINE = f"from {RUNTIME_MODULE_NAME} import _j2py_monitor"

__all__ = [
    "RUNTIME_IMPORT_LINE",
    "RUNTIME_IDIV_IMPORT_LINE",
    "RUNTIME_MONITOR_IMPORT_LINE",
    "RUNTIME_MODULE_NAME",
    "RUNTIME_TODO_IMPORT_LINE",
    "Comparator",
    "MalformedObjectNameException",
    "ObjectName",
    "__j2py_todo__",
    "_j2py_idiv",
    "_j2py_monitor",
    "overloaded",
    "runtime_module_source",
]


def runtime_module_source() -> str:
    """Return the source of the vendored runtime module for output emission."""
    return (Path(__file__).parent / "j2py_runtime.py").read_text()
