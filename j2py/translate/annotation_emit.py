"""Annotation diagnostic and comment emission for stripped Java annotations."""

from __future__ import annotations

from j2py.config.loader import TranslationConfig
from j2py.parse.java_ast import JavaNode
from j2py.translate.diagnostics import TranslationDiagnostics
from j2py.translate.node_utils import first_child_by_type

_FRAMEWORK_ANNOTATIONS = frozenset(
    {
        "Autowired",
        "Bean",
        "Column",
        "Component",
        "Configuration",
        "DeleteMapping",
        "Entity",
        "GetMapping",
        "Id",
        "PathVariable",
        "PostMapping",
        "PutMapping",
        "Qualifier",
        "Repository",
        "RequestMapping",
        "RestController",
        "Service",
        "Table",
        "Transactional",
        "Value",
    }
)


def annotation_nodes(node: JavaNode) -> list[JavaNode]:
    annotations: list[JavaNode] = []
    for modifiers in node.children_by_type("modifiers"):
        for annotation in modifiers.named_children:
            if annotation.type in {"annotation", "marker_annotation"}:
                annotations.append(annotation)
    return annotations


def annotation_names(node: JavaNode) -> list[str]:
    names: list[str] = []
    for annotation in annotation_nodes(node):
        name = _annotation_simple_name(annotation)
        if name is not None:
            names.append(name)
    return names


def annotation_comment_lines(
    node: JavaNode,
    cfg: TranslationConfig,
    *,
    indent: str = "",
) -> list[str]:
    if not cfg.emit_line_comments:
        return []
    lines: list[str] = []
    for annotation in annotation_nodes(node):
        for line in annotation.text.strip().splitlines():
            stripped = line.strip()
            lines.append(f"{indent}# {stripped}" if stripped else f"{indent}#")
    return lines


def record_annotation_diagnostics(
    node: JavaNode,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
    *,
    target_kind: str | None = None,
    target_name: str | None = None,
) -> None:
    for annotation in annotation_nodes(node):
        annotation_name = _annotation_simple_name(annotation)
        if annotation_name is None:
            continue
        if annotation_name in cfg.drop_annotations:
            diagnostics.warn(annotation, reason=f"dropped annotation @{annotation_name}")
            continue
        if annotation_name in _FRAMEWORK_ANNOTATIONS and target_kind and target_name:
            diagnostics.warn(
                annotation,
                reason=(
                    f"stripped framework annotation @{annotation_name} "
                    f"on {target_kind} {target_name}"
                ),
            )
            continue
        diagnostics.warn(annotation, reason=f"unsupported annotation @{annotation_name}")


def _annotation_simple_name(annotation: JavaNode) -> str | None:
    name_node = annotation.child_by_field("name")
    if name_node is None:
        name_node = first_child_by_type(annotation, "identifier", "scoped_identifier")
    if name_node is None:
        return None
    text = name_node.text
    return text.rsplit(".", 1)[-1] if "." in text else text
