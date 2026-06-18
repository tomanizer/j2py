"""Spring/Jackson DTO detection for deterministic Pydantic model promotion."""

from __future__ import annotations

from j2py.config.loader import TranslationConfig
from j2py.parse.java_ast import JavaNode
from j2py.translate.annotation_emit import annotation_nodes
from j2py.translate.framework_annotations import annotation_simple_name
from j2py.translate.java_types import java_type_simple_name

_JACKSON_MODEL_ANNOTATIONS = frozenset({"JsonDeserialize", "JsonSerialize"})
_REQUEST_BODY_ANNOTATIONS = frozenset({"RequestBody"})
_RESPONSE_MAPPING_ANNOTATIONS = frozenset(
    {"DeleteMapping", "GetMapping", "PatchMapping", "PostMapping", "PutMapping", "RequestMapping"}
)
_DTO_BASE_CLASS_NAMES = frozenset({"BaseDto", "BaseDTO", "BaseEntity", "ValidatableEntity"})
_NON_MODEL_RETURN_TYPES = frozenset({"ResponseEntity", "void", "Void"})


def collect_pydantic_model_class_names(root: JavaNode, cfg: TranslationConfig) -> set[str]:
    """Return Java class names that should be emitted as Pydantic models."""

    declared_names = _declared_class_names(root)
    model_names: set[str] = set()
    for node in root.walk():
        if node.type == "class_declaration":
            name = _class_name(node)
            if name is None:
                continue
            if _has_annotation(node, _JACKSON_MODEL_ANNOTATIONS) or _extends_dto_base(node):
                model_names.add(name)
            continue
        if node.type != "method_declaration":
            continue
        model_names.update(_request_body_parameter_types(node, declared_names))
        response_type = _response_body_return_type(node, declared_names, cfg)
        if response_type is not None:
            model_names.add(response_type)
    return model_names


def _declared_class_names(root: JavaNode) -> set[str]:
    return {
        name
        for node in root.walk()
        if node.type == "class_declaration"
        for name in [_class_name(node)]
        if name is not None
    }


def _class_name(node: JavaNode) -> str | None:
    name_node = node.child_by_field("name")
    return name_node.text if name_node is not None else None


def _has_annotation(node: JavaNode, names: frozenset[str]) -> bool:
    return any(annotation_simple_name(annotation) in names for annotation in annotation_nodes(node))


def _extends_dto_base(node: JavaNode) -> bool:
    superclass = node.child_by_field("superclass")
    if superclass is None:
        return False
    return java_type_simple_name(superclass.text) in _DTO_BASE_CLASS_NAMES


def _request_body_parameter_types(node: JavaNode, declared_names: set[str]) -> set[str]:
    params = node.child_by_field("parameters")
    if params is None:
        return set()
    model_names: set[str] = set()
    for param in params.named_children:
        if param.type not in {"formal_parameter", "spread_parameter"}:
            continue
        if not _has_annotation(param, _REQUEST_BODY_ANNOTATIONS):
            continue
        type_node = param.child_by_field("type")
        if type_node is None:
            continue
        type_name = java_type_simple_name(type_node.text)
        if type_name in declared_names:
            model_names.add(type_name)
    return model_names


def _response_body_return_type(
    node: JavaNode,
    declared_names: set[str],
    cfg: TranslationConfig,
) -> str | None:
    if not _has_annotation(node, _RESPONSE_MAPPING_ANNOTATIONS):
        return None
    if any(
        annotation_simple_name(annotation) in cfg.annotation_map
        for annotation in annotation_nodes(node)
    ):
        return None
    type_node = node.child_by_field("type")
    if type_node is None:
        return None
    type_name = java_type_simple_name(type_node.text)
    if type_name in _NON_MODEL_RETURN_TYPES:
        return None
    return type_name if type_name in declared_names else None
