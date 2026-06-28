"""SQLAlchemy persistence scaffolding generation target."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

from j2py.wire.schema import WiringElement, WiringSidecar
from j2py.wire.targets.common import GENERATED_HEADER
from j2py.wiring_contract import translate_field_name

DB_FILENAME = "db.py"
PERSISTENCE_FILENAME = "persistence.py"

_JDBC_TYPES = {
    "DataSource",
    "JdbcTemplate",
    "NamedParameterJdbcTemplate",
    "PlatformTransactionManager",
    "DataSourceTransactionManager",
}
_JDBC_PARAMETER_NAMES = {
    "data_source",
    "jdbc_template",
    "named_parameter_jdbc_template",
    "named_jdbc_template",
    "transaction_manager",
}
_JDBC_PLACEHOLDER_ATTRS = {
    "jdbc_template_connection",
    "named_jdbc_template_connection",
}


@dataclass(frozen=True)
class ConstructorParameterSpec:
    name: str
    python_type: str


@dataclass(frozen=True)
class JdbcBeanSpec:
    name: str
    python_name: str
    java_type: str
    python_type: str
    properties: dict[str, str]
    dependencies: list[str]


@dataclass(frozen=True)
class RepositoryPersistenceSpec:
    identity: str
    provider_name: str
    class_name: str
    module: str
    constructor_parameters: list[ConstructorParameterSpec]
    jdbc_placeholders: list[str]


class SQLAlchemyTarget:
    """Generate SQLAlchemy persistence scaffolding from Spring wiring sidecars."""

    def __init__(self, *, translated_root: Path) -> None:
        self.translated_root = translated_root

    def generate(self, sidecars: list[WiringSidecar], output_dir: Path) -> list[Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        jdbc_beans = jdbc_bean_specs(sidecars)
        repositories = repository_persistence_specs(sidecars, self.translated_root)

        db_path = output_dir / DB_FILENAME
        db_path.write_text(render_db(jdbc_beans, transaction_facts(sidecars)), encoding="utf-8")

        persistence_path = output_dir / PERSISTENCE_FILENAME
        persistence_path.write_text(
            render_persistence(repositories),
            encoding="utf-8",
        )

        return [db_path, persistence_path]


def jdbc_bean_specs(sidecars: list[WiringSidecar]) -> list[JdbcBeanSpec]:
    """Return JDBC bean facts recorded in Spring sidecars."""
    specs: list[JdbcBeanSpec] = []
    for sidecar in sidecars:
        for element in sidecar.elements:
            jdbc_bean = element.spring.get("jdbc_bean")
            if not isinstance(jdbc_bean, dict):
                continue
            specs.append(
                JdbcBeanSpec(
                    name=_str(jdbc_bean.get("name"), default=element.java_name),
                    python_name=_str(
                        jdbc_bean.get("python_name"),
                        default=translate_field_name(element.java_name),
                    ),
                    java_type=_str(jdbc_bean.get("java_type"), default="object"),
                    python_type=_str(jdbc_bean.get("python_type"), default="object"),
                    properties=_properties(jdbc_bean.get("properties")),
                    dependencies=_dependencies(jdbc_bean.get("dependencies")),
                ),
            )
    return sorted(specs, key=lambda spec: (spec.python_name, spec.name))


def repository_persistence_specs(
    sidecars: list[WiringSidecar],
    translated_root: Path,
) -> list[RepositoryPersistenceSpec]:
    """Return repository construction specs with JDBC placeholder expectations."""
    specs: list[RepositoryPersistenceSpec] = []
    for sidecar in sidecars:
        module = sidecar.python_module(translated_root)
        module_path = Path(sidecar.output)
        for element in sidecar.elements:
            if element.kind != "class" or element.spring.get("role") != "repository":
                continue
            identity = _provider_identity(element)
            specs.append(
                RepositoryPersistenceSpec(
                    identity=identity,
                    provider_name=f"get_{translate_field_name(identity)}",
                    class_name=element.python_name,
                    module=module,
                    constructor_parameters=_constructor_parameters(
                        module_path,
                        element.python_name,
                    ),
                    jdbc_placeholders=_jdbc_placeholders(module_path, element.python_name),
                ),
            )
    return sorted(specs, key=lambda spec: (spec.provider_name, spec.class_name))


def has_sqlalchemy_persistence_facts(
    sidecars: list[WiringSidecar],
    translated_root: Path,
) -> bool:
    """Return whether sidecars/output contain facts consumed by the SQLAlchemy target."""
    return bool(
        jdbc_bean_specs(sidecars)
        or repository_persistence_specs(sidecars, translated_root)
        or transaction_facts(sidecars)
    )


def transaction_facts(sidecars: list[WiringSidecar]) -> list[str]:
    """Return Spring transaction facts that require project-owned policy."""
    facts: set[str] = set()
    for sidecar in sidecars:
        for element in sidecar.elements:
            for annotation in element.annotations:
                if _annotation_simple_name(annotation) == "Transactional":
                    facts.add(f"@Transactional on {element.java_name}")
            jdbc_bean = element.spring.get("jdbc_bean")
            if not isinstance(jdbc_bean, dict):
                continue
            java_type = _str(jdbc_bean.get("java_type"), default="")
            python_name = _str(jdbc_bean.get("python_name"), default=element.python_name)
            if "TransactionManager" in java_type or "transaction_manager" in python_name:
                facts.add(python_name)
            for constructor_arg in _list_of_dicts(jdbc_bean.get("constructor_args")):
                arg_type = _str(constructor_arg.get("type"), default="")
                if "TransactionManager" in arg_type:
                    facts.add(python_name)
    return sorted(facts)


def render_db(jdbc_beans: list[JdbcBeanSpec], transaction_names: list[str]) -> str:
    """Render SQLAlchemy engine/session scaffold source."""
    datasource_properties = {
        spec.python_name: spec.properties
        for spec in jdbc_beans
        if _is_data_source(spec) or spec.properties
    }
    jdbc_topology = {
        spec.python_name: {
            "java_type": spec.java_type,
            "python_type": spec.python_type,
            "dependencies": spec.dependencies,
        }
        for spec in jdbc_beans
    }
    lines = [
        GENERATED_HEADER,
        "from __future__ import annotations",
        "",
        "import os",
        "from collections.abc import Iterator",
        "from contextlib import contextmanager",
        "",
        "from sqlalchemy import create_engine",
        "from sqlalchemy.engine import Connection, Engine",
        "from sqlalchemy.orm import Session, sessionmaker",
        "",
        'DATABASE_URL_ENV = "DATABASE_URL"',
        "# TODO(j2py): replace DATABASE_URL with the project database settings source.",
        'DEFAULT_DATABASE_URL = "sqlite+pysqlite:///:memory:"',
        "",
        f"DATASOURCE_PROPERTIES: dict[str, dict[str, str]] = {_repr(datasource_properties)}",
        f"JDBC_BEAN_TOPOLOGY: dict[str, dict[str, object]] = {_repr(jdbc_topology)}",
        f"TRANSACTION_FACTS: tuple[str, ...] = {_tuple_literal(transaction_names)}",
        "",
        "",
        "def database_url() -> str:",
        "    return os.environ.get(DATABASE_URL_ENV, DEFAULT_DATABASE_URL)",
        "",
        "",
        "def create_application_engine(url: str | None = None) -> Engine:",
        "    # TODO(j2py): configure dialect, pool, credentials, retries, and secrets here.",
        "    return create_engine(url or database_url())",
        "",
        "",
        "engine = create_application_engine()",
        "SessionLocal = sessionmaker(engine, autoflush=False)",
        "",
        "",
        "@contextmanager",
        "def session_scope() -> Iterator[Session]:",
        "    session = SessionLocal()",
        "    try:",
        "        yield session",
        "        session.commit()",
        "    except Exception:",
        "        session.rollback()",
        "        raise",
        "    finally:",
        "        session.close()",
        "",
        "",
        "@contextmanager",
        "def connection_scope() -> Iterator[Connection]:",
        "    with engine.begin() as connection:",
        "        yield connection",
    ]
    if transaction_names:
        lines.extend(
            [
                "",
                "",
                "# TODO(j2py): Spring transaction facts were detected. Map @Transactional",
                "# rollback rules, propagation, isolation, and read-only behavior in project code.",
            ],
        )
    return "\n".join(lines).rstrip() + "\n"


def render_persistence(repositories: list[RepositoryPersistenceSpec]) -> str:
    """Render repository/JDBC placeholder binding helpers."""
    imports = _imports_for_repositories(repositories)
    lines = [
        GENERATED_HEADER,
        "from __future__ import annotations",
        "",
        "from sqlalchemy.engine import Connection",
        "",
    ]
    for module in sorted(imports):
        names = ", ".join(sorted(imports[module]))
        lines.append(f"from {module} import {names}")
    if imports:
        lines.append("")
    for index, repository in enumerate(repositories):
        if index:
            lines.extend(["", ""])
        lines.extend(_render_repository_provider(repository))
    if not repositories:
        lines.append("__all__: list[str] = []")
    return "\n".join(lines).rstrip() + "\n"


def missing_placeholder_bindings(
    sidecars: list[WiringSidecar],
    translated_root: Path,
    persistence_source: str,
) -> list[tuple[RepositoryPersistenceSpec, str]]:
    """Return JDBC placeholders expected by repositories but absent from generated source."""
    missing: list[tuple[RepositoryPersistenceSpec, str]] = []
    for repository in repository_persistence_specs(sidecars, translated_root):
        for placeholder in repository.jdbc_placeholders:
            if f"repository.{placeholder} = connection" not in persistence_source:
                missing.append((repository, placeholder))
    return missing


def _render_repository_provider(repository: RepositoryPersistenceSpec) -> list[str]:
    signature_parameters = ["connection: Connection"]
    signature_parameters.extend(
        f"{param.name}: {param.python_type}"
        for param in repository.constructor_parameters
        if not _is_jdbc_constructor_parameter(param)
    )
    constructor_args = [
        "connection" if _is_jdbc_constructor_parameter(param) else param.name
        for param in repository.constructor_parameters
    ]
    lines = [
        (
            f"def {repository.provider_name}("
            f"{', '.join(signature_parameters)}) -> {repository.class_name}:"
        ),
        f"    repository = {repository.class_name}({', '.join(constructor_args)})",
    ]
    if not repository.jdbc_placeholders:
        lines.append(
            "    # TODO(j2py): no JDBC connection placeholders were found on this repository.",
        )
    for placeholder in repository.jdbc_placeholders:
        lines.append(f"    repository.{placeholder} = connection")
    lines.append("    return repository")
    return lines


def _imports_for_repositories(
    repositories: list[RepositoryPersistenceSpec],
) -> dict[str, set[str]]:
    imports: dict[str, set[str]] = {}
    for repository in repositories:
        imports.setdefault(repository.module, set()).add(repository.class_name)
    return imports


def _constructor_parameters(path: Path, class_name: str) -> list[ConstructorParameterSpec]:
    tree = _parse_python(path)
    if tree is None:
        return []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for item in node.body:
            if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                return [
                    ConstructorParameterSpec(
                        name=arg.arg,
                        python_type=_annotation_name(arg.annotation),
                    )
                    for arg in item.args.args[1:]
                ]
    return []


def _jdbc_placeholders(path: Path, class_name: str) -> list[str]:
    tree = _parse_python(path)
    if tree is None:
        return []
    placeholders: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for item in ast.walk(node):
            if (
                isinstance(item, ast.Attribute)
                and isinstance(item.value, ast.Name)
                and item.value.id == "self"
                and item.attr in _JDBC_PLACEHOLDER_ATTRS
            ):
                placeholders.add(item.attr)
    return sorted(placeholders)


def _provider_identity(element: WiringElement) -> str:
    component_name = element.spring.get("component_name")
    if isinstance(component_name, str) and component_name:
        return component_name
    return translate_field_name(element.python_name)


def _is_jdbc_constructor_parameter(param: ConstructorParameterSpec) -> bool:
    return (
        translate_field_name(param.name) in _JDBC_PARAMETER_NAMES
        or _base_type(param.python_type) in _JDBC_TYPES
    )


def _annotation_name(annotation: ast.expr | None) -> str:
    if annotation is not None:
        return ast.unparse(annotation)
    return "object"


def _base_type(type_name: str) -> str:
    base = re.split(r"[\[|]", type_name, maxsplit=1)[0].strip().strip("\"'")
    return base.rsplit(".", maxsplit=1)[-1]


def _is_data_source(spec: JdbcBeanSpec) -> bool:
    return spec.java_type == "DataSource" or spec.python_type == "DataSource"


def _properties(value: object) -> dict[str, str]:
    properties: dict[str, str] = {}
    for item in _list_of_dicts(value):
        target = item.get("target")
        key = item.get("key")
        if isinstance(target, str) and isinstance(key, str):
            properties[target] = key
    return dict(sorted(properties.items()))


def _dependencies(value: object) -> list[str]:
    dependencies: list[str] = []
    for item in _list_of_dicts(value):
        name = item.get("name")
        if isinstance(name, str):
            dependencies.append(name)
    return sorted(dependencies)


def _list_of_dicts(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _annotation_simple_name(annotation: dict[str, object]) -> str:
    simple = annotation.get("simple_name")
    if isinstance(simple, str):
        return simple
    name = annotation.get("name")
    if isinstance(name, str):
        return name.rsplit(".", maxsplit=1)[-1]
    return ""


def _parse_python(path: Path) -> ast.Module | None:
    if not path.is_file():
        return None
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return None


def _repr(value: object) -> str:
    return repr(value)


def _tuple_literal(values: list[str]) -> str:
    if not values:
        return "()"
    return repr(tuple(values))


def _str(value: object, *, default: str) -> str:
    return value if isinstance(value, str) else default
