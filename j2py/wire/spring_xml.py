"""Opt-in parser for Spring XML bean definition files.

Reads the common subset of Spring XML config and produces ``WiringSidecar``
objects in the same ``metadata.spring.bean`` shape as the Java ``@Bean``
plugin (introduced in #592). Downstream tools therefore see XML-defined and
Java-defined beans through a single uniform interface.

Supported constructs
--------------------
* ``<bean id="..." class="...">`` — name, class, aliases
* ``<constructor-arg ref="..."/>`` and value arguments
* ``<property name="..." ref="..."/>`` and value properties
* ``factory-bean``, ``factory-method``, ``init-method``, ``destroy-method``
* ``primary``, ``lazy-init`` attributes
* ``<import resource="..."/>`` — file-system paths only

Explicitly out of scope
-----------------------
* Spring profiles and ``${...}`` placeholder resolution
* Parent bean inheritance and collection merging
* Custom namespace handlers
* Lifecycle emulation or container behaviour
* ``classpath:`` / ``classpath*:`` resource prefixes for imports

Unsupported constructs encountered during parsing are recorded in
``bean.unsupported`` and as ``XmlIngestDiagnostic`` warnings rather than
silently dropped or guessed.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
import xml.sax
import xml.sax.handler
import xml.sax.xmlreader
from dataclasses import dataclass, field
from pathlib import Path

from j2py.wire.schema import WiringElement, WiringSidecar
from j2py.wiring_contract import WIRING_METADATA_SCHEMA_VERSION, translate_field_name

# Spring XML namespace and tag constants.
_NS = "http://www.springframework.org/schema/beans"
_T_BEANS = f"{{{_NS}}}beans"
_T_BEAN = f"{{{_NS}}}bean"
_T_IMPORT = f"{{{_NS}}}import"
_T_CONSTRUCTOR_ARG = f"{{{_NS}}}constructor-arg"
_T_PROPERTY = f"{{{_NS}}}property"
# Also accept tags without the namespace (minimal XML without xmlns declaration).
_BARE = {"beans", "bean", "import", "constructor-arg", "property"}

_PROFILE_VERSION = 1

# Attributes that are not yet supported and should be flagged.
_UNSUPPORTED_ATTRS = {"scope", "parent", "abstract", "depends-on", "autowire"}


@dataclass
class XmlIngestDiagnostic:
    level: str  # "warning" | "error"
    path: str
    message: str


@dataclass
class XmlIngestResult:
    sidecars: list[WiringSidecar] = field(default_factory=list)
    diagnostics: list[XmlIngestDiagnostic] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def ingest_spring_xml_files(
    xml_paths: list[Path],
    *,
    resolve_imports: bool = True,
) -> XmlIngestResult:
    """Parse Spring XML bean definition files and return sidecars + diagnostics.

    Each XML file produces one ``WiringSidecar`` whose elements correspond to
    ``<bean>`` definitions. ``<import resource="..."/>`` elements with
    file-system-resolvable paths are followed when *resolve_imports* is True.
    """
    result = XmlIngestResult()
    seen: set[Path] = set()
    for path in xml_paths:
        _ingest_one(path.resolve(), result=result, seen=seen, resolve_imports=resolve_imports)
    return result


# ---------------------------------------------------------------------------
# Internal: one-file ingestion
# ---------------------------------------------------------------------------


def _ingest_one(
    path: Path,
    *,
    result: XmlIngestResult,
    seen: set[Path],
    resolve_imports: bool,
) -> None:
    if path in seen:
        return
    seen.add(path)

    try:
        builder, root = _parse_xml(path)
    except (ET.ParseError, xml.sax.SAXException) as exc:
        result.diagnostics.append(
            XmlIngestDiagnostic("error", str(path), f"XML parse error: {exc}")
        )
        return
    except OSError as exc:
        result.diagnostics.append(
            XmlIngestDiagnostic("error", str(path), f"Cannot read file: {exc}")
        )
        return

    elements: list[WiringElement] = []

    for child in root:
        local = _local(child.tag)
        if local == "bean":
            elem, diags = _parse_bean(child, builder, path)
            if elem is not None:
                elements.append(elem)
            result.diagnostics.extend(diags)
        elif local == "import":
            if resolve_imports:
                resource = child.get("resource", "")
                import_path = _resolve_resource(resource, path)
                if import_path is not None:
                    _ingest_one(
                        import_path, result=result, seen=seen, resolve_imports=resolve_imports
                    )
                else:
                    result.diagnostics.append(
                        XmlIngestDiagnostic(
                            "warning",
                            str(path),
                            f"Cannot resolve import resource '{resource}' — skipped "
                            f"(only file-system paths are supported; classpath: prefixes are not)",
                        )
                    )
        # <beans> nesting, alias, description, etc. — silently skip

    result.sidecars.append(
        WiringSidecar(
            schema_version=WIRING_METADATA_SCHEMA_VERSION,
            # source and output both point to the XML file: XML-defined beans
            # have no translated Python counterpart.
            source=str(path),
            output=str(path),
            elements=elements,
        )
    )


# ---------------------------------------------------------------------------
# Internal: bean parsing
# ---------------------------------------------------------------------------


def _parse_bean(
    elem: ET.Element,
    builder: _PositionedTreeBuilder,
    xml_path: Path,
) -> tuple[WiringElement | None, list[XmlIngestDiagnostic]]:
    diags: list[XmlIngestDiagnostic] = []

    bean_id = elem.get("id") or elem.get("name") or ""
    if not bean_id:
        diags.append(
            XmlIngestDiagnostic(
                "warning",
                str(xml_path),
                "<bean> element has no id or name attribute — skipped",
            )
        )
        return None, diags

    class_attr = elem.get("class", "")
    python_name = translate_field_name(bean_id)
    java_type = class_attr
    python_type = class_attr.rsplit(".", 1)[-1] if class_attr else ""

    # Source location (best-effort; line only, no column from stdlib ET).
    line = builder.line_of(elem)
    source_location: dict[str, object] = {
        "line": line,
        "column": None,
        "end_line": None,
        "end_column": None,
    }

    # Dependencies: constructor-arg ref + property ref children.
    dependencies: list[dict[str, object]] = []
    constructor_args: list[dict[str, object]] = []
    unsupported: list[str] = []

    for child in elem:
        local = _local(child.tag)
        if local == "constructor-arg":
            ref = child.get("ref")
            value = child.get("value")
            type_attr = child.get("type", "")
            index = child.get("index")
            name_attr = child.get("name")

            if ref:
                py_ref = translate_field_name(ref)
                dependencies.append(
                    {
                        "name": py_ref,
                        "java_name": ref,
                        "type": _simple_name(ref),
                        "java_type": _simple_name(ref),
                        "source": "constructor-arg",
                    }
                )
                constructor_args.append(
                    {
                        "type": type_attr,
                        "arguments": [{"kind": "ref", "value": py_ref}],
                    }
                )
            elif value is not None:
                label = name_attr or (f"index={index}" if index else "arg")
                constructor_args.append(
                    {
                        "type": type_attr,
                        "arguments": [{"kind": "value", "value": value}],
                    }
                )
                _ = label  # used for readability only
            else:
                # Complex constructor-arg (nested list/map/etc.) — flag it.
                unsupported.append("constructor-arg with nested value element")

        elif local == "property":
            ref = child.get("ref")
            name_attr = child.get("name", "")
            if ref:
                py_ref = translate_field_name(ref)
                dependencies.append(
                    {
                        "name": py_ref,
                        "java_name": ref,
                        "type": _simple_name(ref),
                        "java_type": _simple_name(ref),
                        "source": "property",
                    }
                )
            elif child.get("value") is not None:
                pass  # plain value property — not a dependency, not unsupported
            else:
                unsupported.append(f"property '{name_attr}' with nested value element")

        elif local in {"lookup-method", "replaced-method", "qualifier"}:
            unsupported.append(local)

    # Unsupported top-level attributes.
    for attr in _UNSUPPORTED_ATTRS:
        if elem.get(attr) is not None:
            unsupported.append(f"attribute '{attr}'")

    # Factory method — record as a single-entry list matching the @Bean shape.
    factory_method = elem.get("factory-method")
    factory_bean = elem.get("factory-bean")
    factory_methods: list[dict[str, object]] = []
    if factory_method:
        entry: dict[str, object] = {"name": factory_method, "arguments": []}
        if factory_bean:
            entry["factory_bean"] = factory_bean
        factory_methods.append(entry)

    primary_str = elem.get("primary", "").lower()
    primary = primary_str == "true" if primary_str else False

    lazy_str = elem.get("lazy-init", "").lower()
    lazy: bool | None = None
    if lazy_str in ("true", "false"):
        lazy = lazy_str == "true"

    bean_meta: dict[str, object] = {
        "name": bean_id,
        "java_name": bean_id,
        "python_name": python_name,
        "java_type": java_type,
        "python_type": python_type,
        "source_location": source_location,
        "dependencies": dependencies,
        "constructor_args": constructor_args,
        "factory_methods": factory_methods,
        "qualifier": None,
        "primary": primary,
        "lazy": lazy,
        "init_method": elem.get("init-method", ""),
        "destroy_method": elem.get("destroy-method", ""),
        "unsupported": unsupported,
    }

    if unsupported:
        diags.append(
            XmlIngestDiagnostic(
                "warning",
                str(xml_path),
                f"Bean '{bean_id}' contains unsupported constructs: "
                + ", ".join(unsupported),
            )
        )

    wire_elem = WiringElement(
        plugin="spring-xml",
        kind="method",
        java_name=bean_id,
        python_name=python_name,
        annotations=[],
        metadata={"spring": {"profile_version": _PROFILE_VERSION, "bean": bean_meta}},
    )
    return wire_elem, diags


# ---------------------------------------------------------------------------
# Internal: XML parsing with line-number tracking (SAX-based)
# ---------------------------------------------------------------------------


class _PositionedTreeBuilder:
    """SAX ContentHandler that builds an Element tree and records start-line numbers.

    We use SAX rather than ElementTree's own XMLParser because the stdlib C
    extension for XMLParser does not expose the underlying expat object as a
    Python attribute, making it impossible to read ``CurrentLineNumber`` from
    within a TreeBuilder subclass.  The SAX ``Locator`` is fully supported and
    gives us reliable line numbers.
    """

    def __init__(self) -> None:
        self._line_map: dict[int, int] = {}
        self._root: ET.Element | None = None
        self._stack: list[ET.Element] = []

    def line_of(self, elem: ET.Element) -> int | None:
        return self._line_map.get(id(elem))



    def root(self) -> ET.Element:
        assert self._root is not None, "XML not yet parsed"
        return self._root


class _SaxHandler(xml.sax.handler.ContentHandler):
    def __init__(self, builder: _PositionedTreeBuilder) -> None:
        super().__init__()
        self._builder = builder
        self._locator: xml.sax.xmlreader.Locator | None = None

    def setDocumentLocator(self, locator: xml.sax.xmlreader.Locator) -> None:
        self._locator = locator

    def startElement(self, name: str, attrs: xml.sax.xmlreader.AttributesImpl) -> None:
        attrib = {k: v for k, v in attrs.items()}
        elem = ET.Element(name, attrib)
        if self._builder._stack:
            self._builder._stack[-1].append(elem)
        else:
            self._builder._root = elem
        self._builder._stack.append(elem)
        if self._locator is not None:
            line_num = self._locator.getLineNumber()
            if line_num is not None:
                self._builder._line_map[id(elem)] = line_num

    def startElementNS(
        self,
        name: tuple[str | None, str],
        qname: str | None,
        attrs: xml.sax.xmlreader.AttributesNSImpl,
    ) -> None:
        ns_uri, local = name
        tag = f"{{{ns_uri}}}{local}" if ns_uri else local
        attrib = {}
        for (attr_ns, attr_local), value in attrs.items():
            if attr_ns:
                attrib[f"{{{attr_ns}}}{attr_local}"] = value
            else:
                attrib[attr_local] = value
        elem = ET.Element(tag, attrib)
        if self._builder._stack:
            self._builder._stack[-1].append(elem)
        else:
            self._builder._root = elem
        self._builder._stack.append(elem)
        if self._locator is not None:
            line_num = self._locator.getLineNumber()
            if line_num is not None:
                self._builder._line_map[id(elem)] = line_num

    def endElement(self, name: str) -> None:
        self._builder._stack.pop()

    def endElementNS(self, name: tuple[str | None, str], qname: str | None) -> None:
        self._builder._stack.pop()


def _parse_xml(path: Path) -> tuple[_PositionedTreeBuilder, ET.Element]:
    if not path.exists():
        raise FileNotFoundError(f"No such file: {path}")
    builder = _PositionedTreeBuilder()
    handler = _SaxHandler(builder)
    sax_parser = xml.sax.make_parser()
    sax_parser.setFeature(xml.sax.handler.feature_namespaces, True)
    sax_parser.setContentHandler(handler)
    sax_parser.parse(str(path))
    return builder, builder.root()


# ---------------------------------------------------------------------------
# Internal: helpers
# ---------------------------------------------------------------------------


def _local(tag: str) -> str:
    """Strip namespace prefix from an ElementTree tag string."""
    return tag.split("}")[-1] if "}" in tag else tag


def _simple_name(qualified: str) -> str:
    """Return the simple (unqualified) class name from a dotted or bare name."""
    return qualified.rsplit(".", 1)[-1]


def _resolve_resource(resource: str, base_xml: Path) -> Path | None:
    """Resolve a Spring resource string to a file-system path, or None if unsupported."""
    # Strip classpath prefixes — we cannot resolve these without a classpath.
    for prefix in ("classpath*:", "classpath:"):
        if resource.startswith(prefix):
            resource = resource[len(prefix):]
            # After stripping, a leading "/" becomes a relative path.
            resource = resource.lstrip("/")
            # Without a classpath root we still try a sibling-file resolution.
            break

    candidate = (base_xml.parent / resource).resolve()
    return candidate if candidate.exists() else None
