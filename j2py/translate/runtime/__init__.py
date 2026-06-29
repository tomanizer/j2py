"""Vendored runtime support emitted next to translated Python output.

``j2py_runtime.py`` is self-contained (stdlib only) so the pipeline can copy
its source verbatim into the output tree. See ADR 0009.
"""

from __future__ import annotations

from pathlib import Path

from j2py.translate.runtime.j2py_runtime import (
    Comparator,
    Consumer,
    MalformedObjectNameException,
    ObjectName,
    RuntimeException,
    StringBuilder,
    __j2py_todo__,
    _j2py_arraycopy,
    _j2py_decode_int,
    _j2py_idiv,
    _j2py_long_hash_code,
    _j2py_monitor,
    bean,
    component,
    configuration,
    configuration_properties,
    controller,
    delete_mapping,
    get_mapping,
    overloaded,
    path_variable,
    post_mapping,
    put_mapping,
    repository,
    request_body,
    request_mapping,
    request_param,
    response_status,
    rest_controller,
    service,
    transactional,
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
    "Consumer",
    "MalformedObjectNameException",
    "ObjectName",
    "RuntimeException",
    "StringBuilder",
    "__j2py_todo__",
    "_j2py_arraycopy",
    "_j2py_decode_int",
    "_j2py_idiv",
    "_j2py_long_hash_code",
    "_j2py_monitor",
    "bean",
    "component",
    "configuration",
    "configuration_properties",
    "controller",
    "delete_mapping",
    "get_mapping",
    "overloaded",
    "path_variable",
    "post_mapping",
    "put_mapping",
    "repository",
    "request_body",
    "request_mapping",
    "request_param",
    "response_status",
    "rest_controller",
    "service",
    "transactional",
    "runtime_module_source",
]


def runtime_module_source() -> str:
    """Return the source of the vendored runtime module for output emission."""
    return (Path(__file__).parent / "j2py_runtime.py").read_text()
