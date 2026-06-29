"""Opt-in parser for Spring XML bean definition files.

Reads the common subset of Spring XML config and produces ``WiringSidecar``
objects in the same ``metadata.spring.bean`` shape as the Java ``@Bean``
plugin (introduced in #592). Downstream tools therefore see XML-defined and
Java-defined beans through a single uniform interface.

Supported constructs
--------------------
* ``<bean id="..." class="...">`` — name and class (``name`` is used as a
  fallback identity when ``id`` is absent; multi-value alias lists are not split)
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

# Element local names are matched after namespace stripping (see ``_local``), so
# both namespaced Spring XML and bare XML without an xmlns declaration are handled.
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

    # Warn when the root <beans> itself carries a profile attribute — its beans
    # will be ingested as unconditional, which is incorrect.
    root_profile = root.get("profile")
    if root_profile:
        result.diagnostics.append(
            XmlIngestDiagnostic(
                "warning",
                str(path),
                f"Root <beans> has profile='{root_profile}' but Spring profiles are not "
                f"respected — beans are ingested as unconditional.",
            )
        )

    # Warn when root <beans> sets default-* attributes that affect all beans but
    # are not respected during ingestion.
    _UNSUPPORTED_DEFAULTS = {
        "default-lazy-init",
        "default-init-method",
        "default-destroy-method",
        "default-autowire",
    }
    active_defaults = sorted(a for a in _UNSUPPORTED_DEFAULTS if root.get(a) is not None)
    if active_defaults:
        result.diagnostics.append(
            XmlIngestDiagnostic(
                "warning",
                str(path),
                f"Root <beans> sets {', '.join(active_defaults)} but bean-level defaults "
                f"are not applied — beans are ingested with explicit settings only.",
            )
        )

    elements: list[WiringElement] = []
    # Top-level <alias name="src" alias="tgt"/> elements, collected for post-processing.
    raw_aliases: list[tuple[str, str]] = []

    for child in root:
        local = _local(child.tag)
        if local == "bean":
            elem, diags = _parse_bean(child, builder, path)
            if elem is not None:
                elements.append(elem)
            result.diagnostics.extend(diags)
        elif local == "alias":
            src = child.get("name", "").strip()
            tgt = child.get("alias", "").strip()
            if src and tgt:
                raw_aliases.append((src, tgt))
            else:
                result.diagnostics.append(
                    XmlIngestDiagnostic(
                        "warning",
                        str(path),
                        "<alias> element is missing 'name' or 'alias' attribute — skipped",
                    )
                )
        elif local == "beans":
            # Nested <beans> (commonly used for profile-conditional sections).
            # Ingesting their content would require profile evaluation, which is
            # out of scope; warn so the caller knows beans may be missing.
            nested_profile = child.get("profile", "")
            detail = f" (profile='{nested_profile}')" if nested_profile else ""
            result.diagnostics.append(
                XmlIngestDiagnostic(
                    "warning",
                    str(path),
                    f"Nested <beans>{detail} is not ingested — nested bean blocks "
                    f"require profile evaluation which is out of scope for this tool.",
                )
            )
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
        # description, property-placeholder, etc. — silently skip

    # Inject top-level <alias> targets into the matching bean's aliases list so
    # that validation can resolve refs by alias name.  We also search previously
    # created sidecars (from <import> children) so that an alias declared in the
    # importing file can refer to a bean defined in an imported file.
    if raw_aliases:
        _inject_aliases(
            elements,
            raw_aliases,
            already_created=result.sidecars,
            path=path,
            diagnostics=result.diagnostics,
        )

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


def _inject_aliases(
    elements: list[WiringElement],
    raw_aliases: list[tuple[str, str]],
    *,
    already_created: list[WiringSidecar],
    path: Path,
    diagnostics: list[XmlIngestDiagnostic],
) -> None:
    """Merge top-level <alias> declarations into the matching bean's aliases list.

    Searches both *elements* (current file) and *already_created* sidecars
    (previously imported files) so that an alias declared in an importing file
    can attach to a bean defined in one of its imports.  The current file's
    elements take precedence when the same name appears in both.  Emits a
    warning for any alias whose source bean cannot be found.
    """
    by_name: dict[str, dict[str, object]] = {}
    # Index imported sidecars first so the current file can override.
    for sidecar in already_created:
        for elem in sidecar.elements:
            bean = elem.spring.get("bean")
            if isinstance(bean, dict) and isinstance(bean.get("name"), str):
                by_name.setdefault(str(bean["name"]), bean)
    # Current file elements take precedence.
    for elem in elements:
        bean = elem.spring.get("bean")
        if isinstance(bean, dict) and isinstance(bean.get("name"), str):
            by_name[str(bean["name"])] = bean

    for src, tgt in raw_aliases:
        bean = by_name.get(src)
        if bean is not None:
            aliases = bean.setdefault("aliases", [])
            if isinstance(aliases, list) and tgt not in aliases:
                aliases.append(tgt)
        else:
            diagnostics.append(
                XmlIngestDiagnostic(
                    "warning",
                    str(path),
                    f"<alias name=\"{src}\"> refers to an unknown bean — alias '{tgt}' not added.",
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

    # Spring XML identity rules:
    # - ``id`` is the canonical name (unique per file).
    # - ``name`` may be comma/semicolon-separated and provides additional aliases.
    #   When no ``id`` is present the first ``name`` value is the canonical name.
    id_attr = (elem.get("id") or "").strip()
    name_attr_raw = (elem.get("name") or "").strip()
    name_parts = [p.strip() for p in name_attr_raw.replace(";", ",").split(",") if p.strip()]

    if id_attr:
        bean_id = id_attr
        aliases_from_name: list[str] = name_parts  # all name values are aliases
    elif name_parts:
        bean_id = name_parts[0]
        aliases_from_name = name_parts[1:]
    else:
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

            # Also handle nested <ref bean="..."/> and <value>...</value> child
            # elements, which are common alternatives to inline attributes.
            if ref is None and value is None:
                ref_elem = _find_child(child, "ref")
                value_elem = _find_child(child, "value")
                if ref_elem is not None:
                    ref = ref_elem.get("bean") or ref_elem.get("local") or ""
                    if not ref:
                        unsupported.append(
                            "constructor-arg with <ref> that has no bean or local attribute"
                        )
                elif value_elem is not None:
                    value = value_elem.text or ""

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
                constructor_args.append(
                    {
                        "type": type_attr,
                        "arguments": [{"kind": "value", "value": value}],
                    }
                )
            else:
                # Complex constructor-arg (nested list/map/etc.) — flag it.
                unsupported.append("constructor-arg with nested value element")

        elif local == "property":
            ref = child.get("ref")
            name_attr = child.get("name", "")

            # Also handle nested <ref bean="..."/> and <value>...</value>.
            if ref is None and child.get("value") is None:
                ref_elem = _find_child(child, "ref")
                value_elem = _find_child(child, "value")
                if ref_elem is not None:
                    ref = ref_elem.get("bean") or ref_elem.get("local") or ""
                    if not ref:
                        unsupported.append(
                            f"property '{name_attr}' with <ref> that has no bean or local attribute"
                        )
                elif value_elem is not None:
                    pass  # nested plain value — not a dependency, not unsupported
                else:
                    unsupported.append(f"property '{name_attr}' with nested value element")

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
                pass  # plain attribute value — not a dependency, not unsupported

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
        # Additional identities (from name="a,b" or top-level <alias> elements).
        # _inject_aliases() may append to this list after _parse_bean returns.
        "aliases": list(aliases_from_name),
        "unsupported": unsupported,
    }

    if unsupported:
        diags.append(
            XmlIngestDiagnostic(
                "warning",
                str(xml_path),
                f"Bean '{bean_id}' contains unsupported constructs: " + ", ".join(unsupported),
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
    """Namespace-aware handler. Parsing always enables ``feature_namespaces``,
    so only the ``*NS`` callbacks are invoked (see ``_parse_xml``)."""

    def __init__(self, builder: _PositionedTreeBuilder) -> None:
        super().__init__()
        self._builder = builder
        self._locator: xml.sax.xmlreader.Locator | None = None

    def setDocumentLocator(self, locator: xml.sax.xmlreader.Locator) -> None:
        self._locator = locator

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

    def characters(self, content: str) -> None:
        if self._builder._stack:
            current = self._builder._stack[-1]
            current.text = (current.text or "") + content

    def endElementNS(self, name: tuple[str | None, str], qname: str | None) -> None:
        self._builder._stack.pop()


def _parse_xml(path: Path) -> tuple[_PositionedTreeBuilder, ET.Element]:
    if not path.exists():
        raise FileNotFoundError(f"No such file: {path}")
    builder = _PositionedTreeBuilder()
    handler = _SaxHandler(builder)
    sax_parser = xml.sax.make_parser()
    sax_parser.setFeature(xml.sax.handler.feature_namespaces, True)
    # Disable external entity expansion for XXE safety. Spring bean XML does not
    # need external entity resolution, and input may come from untrusted source trees.
    sax_parser.setFeature(xml.sax.handler.feature_external_ges, False)
    sax_parser.setFeature(xml.sax.handler.feature_external_pes, False)
    sax_parser.setContentHandler(handler)
    sax_parser.parse(str(path))
    return builder, builder.root()


# Helper functions for XML element lookup and path resolution.


def _find_child(elem: ET.Element, local_name: str) -> ET.Element | None:
    """Return the first direct child whose local tag name matches *local_name*."""
    return next((c for c in elem if _local(c.tag) == local_name), None)


def _local(tag: str) -> str:
    """Strip namespace prefix from an ElementTree tag string."""
    return tag.split("}")[-1] if "}" in tag else tag


def _simple_name(qualified: str) -> str:
    """Return the simple (unqualified) class name from a dotted or bare name."""
    return qualified.rsplit(".", 1)[-1]


def _resolve_resource(resource: str, base_xml: Path) -> Path | None:
    """Resolve a Spring resource string to a file-system path, or None if unsupported.

    Returns None for ``classpath:`` / ``classpath*:`` imports — we have no
    classpath to resolve against, so the caller emits a warning rather than
    guessing at a sibling file that may or may not be the intended resource.
    """
    if resource.startswith(("classpath:", "classpath*:")):
        return None

    candidate = (base_xml.parent / resource).resolve()
    return candidate if candidate.is_file() else None
