"""Central import policy for Java types that are not Python modules."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from j2py.translate.rules.naming import translate_class_name

if TYPE_CHECKING:
    from j2py.config.loader import TranslationConfig


ImportPolicySource = Literal[
    "drop_import",
    "import_map",
    "java_lang_builtin",
    "platform_placeholder",
    "external_placeholder",
]


@dataclass(frozen=True)
class ImportPolicy:
    """Resolved handling for one Java import or implicit platform type."""

    java_name: str
    python_name: str
    import_lines: tuple[str, ...] = ()
    source: ImportPolicySource = "platform_placeholder"


JAVA_LANG_BUILTINS: frozenset[str] = frozenset(
    {
        "java.lang.Boolean",
        "java.lang.Byte",
        "java.lang.Character",
        "java.lang.CharSequence",
        "java.lang.Class",
        "java.lang.Cloneable",
        "java.lang.Comparable",
        "java.lang.Double",
        "java.lang.Float",
        "java.lang.Integer",
        "java.lang.Iterable",
        "java.lang.Long",
        "java.lang.Math",
        "java.lang.Number",
        "java.lang.Object",
        "java.lang.Serializable",
        "java.lang.Short",
        "java.lang.String",
        "java.lang.StringBuffer",
        "java.lang.StringBuilder",
        "java.lang.System",
    },
)


PLATFORM_PLACEHOLDER_TYPES: frozenset[str] = frozenset(
    {
        "java.util.Comparator",
        "java.util.Objects",
        "java.util.concurrent.Callable",
        "javax.management.MalformedObjectNameException",
        "javax.management.ObjectName",
    },
)


PLACEHOLDER_IMPORTS: dict[str, str] = {
    "java.util.Comparator": "from typing import Protocol as Comparator",
    "java.util.concurrent.Callable": "from collections.abc import Callable",
    "javax.management.MalformedObjectNameException": (
        "from typing import Any as MalformedObjectNameException"
    ),
    "javax.management.ObjectName": "from typing import Any as ObjectName",
    "org.springframework.core.NativeDetector": "from typing import Any as NativeDetector",
}


EXTERNAL_PLACEHOLDER_TYPES: frozenset[str] = frozenset(
    {
        "org.springframework.core.NativeDetector",
    },
)


def java_import_policy(java_name: str, cfg: TranslationConfig) -> ImportPolicy | None:
    """Return deterministic policy for a Java type import, if it is non-project."""

    raw_name = java_name.rsplit(".", 1)[-1]
    py_name = translate_class_name(raw_name)

    if java_name in cfg.drop_imports:
        return ImportPolicy(
            java_name=java_name,
            python_name=py_name,
            source="drop_import",
        )

    mapped = cfg.import_map.get(java_name)
    if mapped is not None:
        return ImportPolicy(
            java_name=java_name,
            python_name=python_binding_from_import_map(mapped) or py_name,
            import_lines=tuple(line.strip() for line in mapped.splitlines() if line.strip()),
            source="import_map",
        )

    implicit = implicit_java_lang_type_policy(raw_name)
    if implicit is not None and java_name == implicit.java_name:
        return implicit

    if java_name in PLATFORM_PLACEHOLDER_TYPES:
        mapped = PLACEHOLDER_IMPORTS.get(java_name, "")
        return ImportPolicy(
            java_name=java_name,
            python_name=python_binding_from_import_map(mapped) or py_name,
            import_lines=tuple(line.strip() for line in mapped.splitlines() if line.strip()),
            source="platform_placeholder",
        )

    if java_name in EXTERNAL_PLACEHOLDER_TYPES:
        mapped = PLACEHOLDER_IMPORTS.get(java_name, "")
        return ImportPolicy(
            java_name=java_name,
            python_name=python_binding_from_import_map(mapped) or py_name,
            import_lines=tuple(line.strip() for line in mapped.splitlines() if line.strip()),
            source="external_placeholder",
        )

    return None


def implicit_java_lang_type_policy(raw_name: str) -> ImportPolicy | None:
    """Return policy for implicit ``java.lang`` type references."""

    java_name = f"java.lang.{raw_name}"
    if java_name not in JAVA_LANG_BUILTINS:
        return None
    return ImportPolicy(
        java_name=java_name,
        python_name=translate_class_name(raw_name),
        source="java_lang_builtin",
    )


def python_binding_from_import_map(import_text: str) -> str | None:
    """Return the visible Python name introduced by a configured import snippet."""

    for line in import_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            module = ast.parse(stripped)
        except SyntaxError:
            continue
        if len(module.body) != 1:
            continue
        statement = module.body[0]
        if isinstance(statement, ast.ImportFrom) and statement.names:
            alias = statement.names[0]
            return alias.asname or alias.name
        if isinstance(statement, ast.Import) and statement.names:
            alias = statement.names[0]
            return alias.asname or alias.name.split(".", 1)[0]
    return None
