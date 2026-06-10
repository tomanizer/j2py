"""Symbol table: track declared types, fields, and methods per Java file."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from j2py.parse.java_ast import JavaNode, ParsedFile


@dataclass
class FieldSymbol:
    name: str
    java_type: str
    is_static: bool = False
    is_final: bool = False
    line: int = 0


@dataclass
class MethodSymbol:
    name: str
    return_type: str
    param_types: list[str] = field(default_factory=list)
    param_names: list[str] = field(default_factory=list)
    is_static: bool = False
    is_abstract: bool = False
    throws: list[str] = field(default_factory=list)
    line: int = 0


@dataclass
class ClassSymbol:
    name: str
    package: str
    superclass: str | None = None
    interfaces: list[str] = field(default_factory=list)
    is_interface: bool = False
    is_abstract: bool = False
    is_enum: bool = False
    fields: list[FieldSymbol] = field(default_factory=list)
    methods: list[MethodSymbol] = field(default_factory=list)
    inner_classes: list[ClassSymbol] = field(default_factory=list)
    line: int = 0


@dataclass
class FileSymbols:
    path: Path
    package: str
    imports: list[str] = field(default_factory=list)
    classes: list[ClassSymbol] = field(default_factory=list)


def extract_symbols(parsed: ParsedFile) -> FileSymbols:
    """Walk the parsed Java AST and build a symbol table for the file."""
    root = parsed.root
    package = _extract_package(root)
    imports = _extract_imports(root)
    classes = _extract_classes(root, package)
    return FileSymbols(path=parsed.path, package=package, imports=imports, classes=classes)


def _extract_package(root: JavaNode) -> str:
    for node in root.find_all("package_declaration"):
        for child in node.walk():
            if child.type in ("scoped_identifier", "identifier"):
                return child.text
    return ""


def _extract_imports(root: JavaNode) -> list[str]:
    result: list[str] = []
    for node in root.find_all("import_declaration"):
        for child in node.walk():
            if child.type in ("scoped_identifier", "identifier"):
                result.append(child.text)
                break
    return result


def _extract_classes(root: JavaNode, package: str) -> list[ClassSymbol]:
    classes: list[ClassSymbol] = []
    declaration_types = {
        "class_declaration",
        "interface_declaration",
        "enum_declaration",
        "annotation_type_declaration",
    }
    for node in root.named_children:
        if node.type not in declaration_types:
            continue
        cls = _parse_class(node, package)
        if cls:
            classes.append(cls)
    return classes


def _parse_class(node: JavaNode, package: str) -> ClassSymbol | None:
    name_node = node.child_by_field("name")
    if not name_node:
        return None

    modifiers = {c.text for c in node.children_by_type("modifiers")}
    is_interface = node.type == "interface_declaration"
    is_enum = node.type == "enum_declaration"
    is_abstract = "abstract" in modifiers

    superclass: str | None = None
    super_node = node.child_by_field("superclass")
    if super_node:
        type_node = super_node.child_by_field("type") or _first_type_name(super_node)
        superclass = type_node.text if type_node else super_node.text

    interfaces: list[str] = []
    iface_node = node.child_by_field("interfaces") or node.child_by_field("extends_interfaces")
    if iface_node:
        for t in iface_node.find_all("type_identifier"):
            interfaces.append(t.text)

    fields: list[FieldSymbol] = []
    methods: list[MethodSymbol] = []
    inner_classes: list[ClassSymbol] = []

    body = node.child_by_field("body")
    if body:
        for child in body.named_children:
            if child.type == "field_declaration":
                fields.extend(_parse_fields(child))
            elif child.type in ("method_declaration", "constructor_declaration"):
                m = _parse_method(child)
                if m:
                    methods.append(m)
            elif child.type in {
                "class_declaration",
                "interface_declaration",
                "enum_declaration",
                "annotation_type_declaration",
            }:
                inner = _parse_class(child, package)
                if inner is not None:
                    inner_classes.append(inner)

    return ClassSymbol(
        name=name_node.text,
        package=package,
        superclass=superclass,
        interfaces=interfaces,
        is_interface=is_interface,
        is_abstract=is_abstract,
        is_enum=is_enum,
        fields=fields,
        methods=methods,
        inner_classes=inner_classes,
        line=node.location.line,
    )


def _first_type_name(node: JavaNode) -> JavaNode | None:
    for child in node.named_children:
        if child.type in {"type_identifier", "scoped_type_identifier", "generic_type"}:
            return child
    return None


def _parse_fields(node: JavaNode) -> list[FieldSymbol]:
    type_node = node.child_by_field("type")
    java_type = type_node.text if type_node else "Object"
    modifiers_text = {c.text for c in node.children_by_type("modifiers")}

    result: list[FieldSymbol] = []
    for declarator in node.find_all("variable_declarator"):
        name_node = declarator.child_by_field("name")
        if name_node:
            result.append(FieldSymbol(
                name=name_node.text,
                java_type=java_type,
                is_static="static" in modifiers_text,
                is_final="final" in modifiers_text,
                line=node.location.line,
            ))
    return result


def _parse_method(node: JavaNode) -> MethodSymbol | None:
    name_node = node.child_by_field("name")
    if not name_node:
        return None

    type_node = node.child_by_field("type")
    return_type = type_node.text if type_node else "void"

    modifiers_text = {c.text for c in node.children_by_type("modifiers")}

    param_types: list[str] = []
    param_names: list[str] = []
    params_node = node.child_by_field("parameters")
    if params_node:
        for param in params_node.find_all("formal_parameter", "spread_parameter"):
            pt = param.child_by_field("type")
            pn = param.child_by_field("name")
            param_types.append(pt.text if pt else "Object")
            param_names.append(pn.text if pn else "_")

    throws: list[str] = []
    throws_node = node.child_by_field("throws")
    if throws_node:
        for t in throws_node.find_all("type_identifier"):
            throws.append(t.text)

    return MethodSymbol(
        name=name_node.text,
        return_type=return_type,
        param_types=param_types,
        param_names=param_names,
        is_static="static" in modifiers_text,
        is_abstract="abstract" in modifiers_text,
        throws=throws,
        line=node.location.line,
    )
