"""Spring Data repository interface lowering."""

from __future__ import annotations

from dataclasses import dataclass

from j2py.config.loader import TranslationConfig
from j2py.parse.java_ast import JavaNode
from j2py.translate.annotation_emit import annotation_nodes
from j2py.translate.class_environment import ClassTranslationEnvironment
from j2py.translate.class_methods import parameter_infos, return_type, signature
from j2py.translate.diagnostics import TranslationDiagnostics
from j2py.translate.framework_annotations import (
    annotation_simple_name,
    annotation_template_values,
)
from j2py.translate.node_utils import first_child_by_type
from j2py.translate.rules.naming import translate_class_name, translate_method_name
from j2py.translate.rules.types import translate_type

_SPRING_DATA_REPOSITORY_BASES = frozenset(
    {
        "CrudRepository",
        "JpaRepository",
        "PagingAndSortingRepository",
        "Repository",
    }
)
_STANDARD_REPOSITORY_METHODS = frozenset(
    {
        "count",
        "delete",
        "existsById",
        "findAll",
        "findById",
        "save",
    }
)


@dataclass(frozen=True)
class SpringDataRepositoryInfo:
    entity_type: str
    id_type: str


def translate_spring_data_repository_interface(
    node: JavaNode,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
    *,
    env: ClassTranslationEnvironment,
) -> list[str] | None:
    """Lower Spring Data repository interfaces to concrete session-backed classes."""
    info = spring_data_repository_info(node, cfg)
    if info is None:
        return None

    diagnostics.imports.need_line("from sqlalchemy import func")
    diagnostics.imports.need_line("from sqlalchemy import select")
    diagnostics.imports.need_line("from sqlalchemy.orm import Session")

    name_node = node.child_by_field("name")
    class_name = translate_class_name(name_node.text if name_node is not None else "Unknown")
    body = node.child_by_field("body")
    methods = (
        []
        if body is None
        else [child for child in body.named_children if child.type == "method_declaration"]
    )

    lines = [f"class {class_name}:"]
    if env.docstring_lines:
        lines.extend(env.docstring_lines)
    if env.docstring_lines:
        lines.append("")
    lines.extend(_constructor_lines(cfg))

    for method in methods:
        raw_name = _method_name(method)
        if raw_name in _STANDARD_REPOSITORY_METHODS:
            diagnostics.record(
                method,
                supported=True,
                reason="translated Spring Data repository CRUD method",
            )
            continue
        lines.append("")
        lines.extend(_query_stub_lines(method, cfg, diagnostics))

    for method_lines in _crud_method_lines(info, cfg):
        lines.append("")
        lines.extend(method_lines)

    return lines


def spring_data_repository_info(
    node: JavaNode,
    cfg: TranslationConfig,
) -> SpringDataRepositoryInfo | None:
    extends_node = first_child_by_type(node, "extends_interfaces")
    if extends_node is None:
        return None
    for generic_type in extends_node.find_all("generic_type"):
        base_name = _generic_base_name(generic_type)
        if base_name not in _SPRING_DATA_REPOSITORY_BASES:
            continue
        type_args = _generic_type_arguments(generic_type)
        if not type_args:
            return None
        entity_type = translate_type(type_args[0].text, cfg)
        id_type = translate_type(type_args[1].text, cfg) if len(type_args) > 1 else "object"
        return SpringDataRepositoryInfo(
            entity_type=entity_type,
            id_type=id_type,
        )
    return None


def _constructor_lines(cfg: TranslationConfig) -> list[str]:
    if cfg.emit_type_hints:
        return [
            "    def __init__(self, session: Session) -> None:",
            "        self._session = session",
        ]
    return [
        "    def __init__(self, session):",
        "        self._session = session",
    ]


def _query_stub_lines(
    method: JavaNode,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
) -> list[str]:
    diagnostics.record(
        method,
        supported=True,
        reason="translated Spring Data repository query method stub",
    )
    params = parameter_infos(method, cfg, diagnostics)
    method_return_type = return_type(method, cfg)
    diagnostics.imports.need_type_annotation(method_return_type)
    for param in params:
        diagnostics.imports.need_type_annotation(param.py_type)

    raw_name = _method_name(method)
    py_name = translate_method_name(raw_name, snake_case=cfg.snake_case_methods)
    rendered_signature = signature(
        py_name,
        params,
        return_type=method_return_type,
        include_self=True,
        emit_type_hints=cfg.emit_type_hints,
    )
    lines = [
        f"    {rendered_signature}:",
    ]
    jpql = _query_annotation_value(method)
    if jpql is not None:
        lines.append("        # TODO(j2py): translate JPQL query")
        lines.append(f"        # JPQL: {jpql}")
    else:
        lines.append(f"        # TODO(j2py): translate Spring Data derived query method {raw_name}")
    lines.append("        raise NotImplementedError")
    return lines


def _crud_method_lines(
    info: SpringDataRepositoryInfo,
    cfg: TranslationConfig,
) -> list[list[str]]:
    entity = info.entity_type
    id_type = info.id_type
    count_return = (
        f"        return self._session.scalar(select(func.count()).select_from({entity})) or 0"
    )
    if cfg.emit_type_hints:
        return [
            [
                f"    def find_by_id(self, id: {id_type}) -> {entity} | None:",
                f"        return self._session.get({entity}, id)",
            ],
            [
                f"    def find_all(self) -> list[{entity}]:",
                f"        return list(self._session.execute(select({entity})).scalars())",
            ],
            [
                f"    def save(self, entity: {entity}) -> {entity}:",
                "        self._session.add(entity)",
                "        self._session.flush()",
                "        return entity",
            ],
            [
                f"    def delete(self, entity: {entity}) -> None:",
                "        self._session.delete(entity)",
            ],
            [
                f"    def exists_by_id(self, id: {id_type}) -> bool:",
                f"        return self._session.get({entity}, id) is not None",
            ],
            [
                "    def count(self) -> int:",
                count_return,
            ],
        ]
    return [
        [
            "    def find_by_id(self, id):",
            f"        return self._session.get({entity}, id)",
        ],
        [
            "    def find_all(self):",
            f"        return list(self._session.execute(select({entity})).scalars())",
        ],
        [
            "    def save(self, entity):",
            "        self._session.add(entity)",
            "        self._session.flush()",
            "        return entity",
        ],
        [
            "    def delete(self, entity):",
            "        self._session.delete(entity)",
        ],
        [
            "    def exists_by_id(self, id):",
            f"        return self._session.get({entity}, id) is not None",
        ],
        [
            "    def count(self):",
            count_return,
        ],
    ]


def _generic_base_name(node: JavaNode) -> str | None:
    for child in node.named_children:
        if child.type in {"type_identifier", "scoped_type_identifier"}:
            return child.text.rsplit(".", 1)[-1]
    return None


def _generic_type_arguments(node: JavaNode) -> list[JavaNode]:
    type_args = first_child_by_type(node, "type_arguments")
    if type_args is None:
        return []
    return [
        child
        for child in type_args.named_children
        if child.type
        in {
            "array_type",
            "boolean_type",
            "floating_point_type",
            "generic_type",
            "integral_type",
            "scoped_type_identifier",
            "type_identifier",
        }
    ]


def _method_name(method: JavaNode) -> str:
    name_node = method.child_by_field("name")
    return name_node.text if name_node is not None else "unknown"


def _query_annotation_value(method: JavaNode) -> str | None:
    for annotation in annotation_nodes(method):
        if annotation_simple_name(annotation) != "Query":
            continue
        values = annotation_template_values(annotation)
        return values.get("value")
    return None
