"""Known Java static imports for deterministic translation."""

from __future__ import annotations

KNOWN_STATIC_FIELD_ALIASES: dict[str, str] = {
    "java.lang.annotation.ElementType.CONSTRUCTOR": "ElementType.CONSTRUCTOR",
    "java.lang.annotation.ElementType.METHOD": "ElementType.METHOD",
    "java.lang.annotation.ElementType.TYPE": "ElementType.TYPE",
    "java.lang.Math.PI": "math.pi",
    "java.lang.Math.E": "math.e",
    "java.lang.Integer.MAX_VALUE": "2**31 - 1",
}

KNOWN_STATIC_METHOD_IMPORTS: frozenset[str] = frozenset(
    {
        "java.lang.Character.isDigit",
        "java.lang.Character.isLetter",
        "java.lang.Character.isLetterOrDigit",
        "java.lang.Character.isLowerCase",
        "java.lang.Character.isUpperCase",
        "java.lang.Character.isWhitespace",
        "java.lang.Integer.compare",
        "java.lang.Math.abs",
        "java.lang.Math.max",
        "java.lang.Math.min",
        "java.lang.Math.pow",
        "java.lang.Math.sqrt",
        "java.lang.Math.floor",
        "java.lang.Math.ceil",
        "java.lang.Math.round",
        "java.lang.Math.log",
        "java.util.Arrays.equals",
        "java.util.Collections.unmodifiableList",
        "java.util.Objects.equals",
        "java.util.Objects.isNull",
        "java.util.Objects.nonNull",
        "java.util.Objects.requireNonNull",
        "com.google.common.base.Preconditions.checkArgument",
        "com.google.common.base.Preconditions.checkNotNull",
        "com.google.common.base.Preconditions.checkState",
    },
)


def known_static_field_alias(imported_name: str) -> str | None:
    return KNOWN_STATIC_FIELD_ALIASES.get(imported_name)


def is_known_static_method_import(imported_name: str) -> bool:
    return imported_name in KNOWN_STATIC_METHOD_IMPORTS
