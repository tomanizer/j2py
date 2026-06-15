"""Type annotation translation: Java type expressions → Python type hints."""

from __future__ import annotations

import re

from j2py.config.loader import TranslationConfig


def translate_type(java_type: str, cfg: TranslationConfig) -> str:
    """Convert a Java type string to its Python equivalent.

    Handles primitives, boxed types, generic collections, arrays, and
    nested generics recursively.

    Examples:
        "int"              → "int"
        "String"           → "str"
        "List<String>"     → "list[str]"
        "Map<String, Integer>" → "dict[str, int]"
        "int[]"            → "list[int]"
        "Optional<String>" → "str | None"
    """
    java_type = _normalize_type_text(_strip_type_annotations(java_type.strip()))

    # Arrays
    if java_type.endswith("[]"):
        inner = translate_type(java_type[:-2], cfg)
        return f"list[{inner}]"

    # Varargs (int...)
    if java_type.endswith("..."):
        inner = translate_type(java_type[:-3], cfg)
        return f"*{inner}"

    # Generic: RawType<...>
    generic_match = re.match(r"^([\w.]+)\s*<(.+)>$", java_type)
    if generic_match:
        raw = _normalize_java_lang_type(generic_match.group(1))
        params_str = generic_match.group(2)
        params = _split_type_params(params_str)

        if raw == "Optional" and len(params) == 1:
            inner = translate_type(params[0], cfg)
            return f"{inner} | None"

        py_raw = cfg.collection_map.get(raw) or cfg.type_map.get(raw) or raw
        py_params = [translate_type(p, cfg) for p in params]

        # Wildcard ? → Any
        py_params = ["Any" if p.strip() in ("?", "? extends Object") else p for p in py_params]

        return f"{py_raw}[{', '.join(py_params)}]"

    # Wildcard alone
    if java_type in ("?", "? extends Object"):
        return "Any"

    if java_type.startswith("? extends "):
        return translate_type(java_type[len("? extends ") :], cfg)

    if java_type.startswith("? super "):
        return translate_type(java_type[len("? super ") :], cfg)

    java_type = _normalize_java_lang_type(java_type)

    # Collection raw types
    if java_type in cfg.collection_map:
        return cfg.collection_map[java_type]

    # Primitives + boxed
    if java_type in cfg.type_map:
        return cfg.type_map[java_type]

    return java_type


def java_default_value(java_type: str) -> str:
    """Return the Java default value expression for a field or sized array element."""
    base_type = _strip_type_annotations(java_type).split("<", 1)[0].strip()
    if base_type.endswith("[]"):
        return "None"
    if base_type in {"byte", "short", "int", "long"}:
        return "0"
    if base_type in {"float", "double"}:
        return "0.0"
    if base_type == "boolean":
        return "False"
    if base_type == "char":
        return r'"\0"'
    return "None"


def _split_type_params(params_str: str) -> list[str]:
    """Split comma-separated type params respecting nested angle brackets."""
    depth = 0
    current: list[str] = []
    result: list[str] = []
    for ch in params_str:
        if ch == "<":
            depth += 1
            current.append(ch)
        elif ch == ">":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            result.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        result.append("".join(current).strip())
    return result


def _strip_type_annotations(java_type: str) -> str:
    """Remove Java type-use annotations such as @Nullable before mapping types."""
    return re.sub(r"@\w+(?:\([^)]*\))?\s*", "", java_type).strip()


def _normalize_type_text(java_type: str) -> str:
    """Collapse Java formatter whitespace that can appear inside generic signatures."""
    return re.sub(r"\s+", " ", java_type).strip()


def _normalize_java_lang_type(java_type: str) -> str:
    """Map fully-qualified java.lang aliases to the simple names in default maps."""
    if java_type.startswith("java.lang."):
        return java_type.removeprefix("java.lang.")
    return java_type


def is_var_type(java_type: str) -> bool:
    """Return True when a Java declaration uses local type inference (`var`)."""
    return _strip_type_annotations(java_type.strip()) == "var"


def element_type_from_container(py_type: str) -> str | None:
    """Return the first type argument for a parameterized container annotation."""
    bracket = py_type.find("[")
    if bracket == -1 or not py_type.endswith("]"):
        return None
    inner = py_type[bracket + 1 : -1]
    depth = 0
    for index, char in enumerate(inner):
        if char in {"<", "["}:
            depth += 1
        elif char in {">", "]"}:
            depth -= 1
        elif char == "," and depth == 0:
            return inner[:index].strip()
    return inner.strip() or None


MAP_LIKE_SIMPLE_NAMES: frozenset[str] = frozenset(
    {
        "AnnotationAttributes",
        "MergedAnnotation",
        "Properties",
    },
)

# Receivers whose `.get(...)` is an API call (reflection, futures), not indexing.
API_GET_RECEIVER_SIMPLE_NAMES: frozenset[str] = frozenset(
    {
        "CompletableFuture",
        "Field",
        "ForkJoinTask",
        "Future",
        "Optional",
        "ScheduledFuture",
    },
)

# Java methods whose return value behaves like a list for `.get(index)` lowering.
LIST_RETURNING_METHOD_NAMES: frozenset[str] = frozenset(
    {
        "asList",
        "getEnumConstants",
        "reverse",
        "subList",
        "toList",
    },
)

# Java methods whose return value behaves like a map for `.get(key)` lowering.
MAP_RETURNING_METHOD_NAMES: frozenset[str] = frozenset(
    {
        "getAll",
        "getAllPresent",
        "getTypeArguments",
        "loadAll",
    },
)

# Null-check helpers that return their first argument unchanged.
NULL_PASS_THROUGH_METHOD_NAMES: frozenset[str] = frozenset(
    {
        "checkNotNull",
        "requireNonNull",
    },
)


def type_simple_name(py_type: str) -> str:
    """Return the unqualified base name from a translated type hint."""
    base = py_type.split("[", 1)[0].strip()
    return base.rsplit(".", 1)[-1]


def is_map_like_type(py_type: str) -> bool:
    """True when a translated type behaves like a Java Map for `.get(key)` lowering."""
    if " | " in py_type:
        return any(
            is_map_like_type(part.strip()) for part in py_type.split("|") if part.strip() != "None"
        )
    if py_type == "dict" or py_type.startswith("dict["):
        return True
    simple = type_simple_name(py_type)
    if simple in MAP_LIKE_SIMPLE_NAMES:
        return True
    return simple.endswith("Map") or simple.endswith("Multimap")


def is_api_get_receiver_type(py_type: str) -> bool:
    """True when `.get(...)` on this receiver is a Java API call, not collection access."""
    if " | " in py_type:
        return any(
            is_api_get_receiver_type(part.strip())
            for part in py_type.split("|")
            if part.strip() != "None"
        )
    simple = type_simple_name(py_type)
    if simple in API_GET_RECEIVER_SIMPLE_NAMES:
        return True
    return simple.endswith("Property") or simple.endswith("PropertyWriter")


def is_list_like_type(py_type: str) -> bool:
    """True when a translated type behaves like a Java List for `.get(index)` lowering."""
    if " | " in py_type:
        return any(
            is_list_like_type(part.strip()) for part in py_type.split("|") if part.strip() != "None"
        )
    if py_type == "list" or py_type.startswith("list["):
        return True
    simple = type_simple_name(py_type)
    return simple.endswith("List") and not simple.endswith("Multimap")


def return_type_from_function(py_type: str) -> str | None:
    """Return the output type parameter from ``Function[Input, Output]``."""
    bracket = py_type.find("[")
    if bracket == -1 or not py_type.endswith("]"):
        return None
    if type_simple_name(py_type.split("[", 1)[0]) != "Function":
        return None
    inner = py_type[bracket + 1 : -1]
    depth = 0
    for index in range(len(inner) - 1, -1, -1):
        char = inner[index]
        if char in {">", "]"}:
            depth += 1
        elif char in {"<", "["}:
            depth -= 1
        elif char == "," and depth == 0:
            return inner[index + 1 :].strip() or None
    return None
