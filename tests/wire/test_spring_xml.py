"""Tests for Spring XML bean definition ingestion."""

from __future__ import annotations

from pathlib import Path

from j2py.wire.spring_xml import XmlIngestResult, ingest_spring_xml_files
from j2py.wire.validation import SpringBeanDefinitionCheck, ValidationContext

FIXTURES = Path(__file__).parent.parent / "fixtures" / "xml"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ingest(filename: str, *, resolve_imports: bool = True) -> XmlIngestResult:
    return ingest_spring_xml_files([FIXTURES / filename], resolve_imports=resolve_imports)


def _beans(result: XmlIngestResult) -> list[dict[str, object]]:
    """Collect all bean metadata dicts across all sidecars."""
    beans = []
    for sidecar in result.sidecars:
        for element in sidecar.elements:
            bean = element.spring.get("bean")
            if isinstance(bean, dict):
                beans.append(bean)
    return beans


# ---------------------------------------------------------------------------
# Basic parsing
# ---------------------------------------------------------------------------


def test_ingest_petclinic_beans_produces_sidecar() -> None:
    result = _ingest("petclinic_beans.xml")
    assert result.diagnostics == []
    assert len(result.sidecars) == 1
    sidecar = result.sidecars[0]
    assert sidecar.schema_version == 1
    assert sidecar.source.endswith("petclinic_beans.xml")
    assert len(sidecar.elements) == 4


def test_bean_plugin_is_spring_xml() -> None:
    result = _ingest("petclinic_beans.xml")
    for element in result.sidecars[0].elements:
        assert element.plugin == "spring-xml"
        assert element.kind == "method"


def test_owner_service_bean_fields() -> None:
    result = _ingest("petclinic_beans.xml")
    beans = {b["name"]: b for b in _beans(result)}

    svc = beans["ownerService"]
    assert svc["java_name"] == "ownerService"
    assert svc["python_name"] == "owner_service"
    assert svc["java_type"] == "com.example.clinic.service.OwnerService"
    assert svc["python_type"] == "OwnerService"
    assert svc["init_method"] == "start"
    assert svc["destroy_method"] == "stop"
    assert svc["primary"] is True
    assert svc["lazy"] is None  # not set


def test_owner_repository_bean_lazy() -> None:
    result = _ingest("petclinic_beans.xml")
    beans = {b["name"]: b for b in _beans(result)}
    repo = beans["ownerRepository"]
    assert repo["lazy"] is True
    assert repo["primary"] is False


def test_constructor_arg_ref_becomes_dependency() -> None:
    result = _ingest("petclinic_beans.xml")
    beans = {b["name"]: b for b in _beans(result)}

    svc = beans["ownerService"]
    assert len(svc["dependencies"]) == 1
    dep = svc["dependencies"][0]
    assert dep["java_name"] == "ownerRepository"
    assert dep["name"] == "owner_repository"
    assert dep["source"] == "constructor-arg"

    assert len(svc["constructor_args"]) == 1
    arg = svc["constructor_args"][0]
    assert arg["arguments"][0]["kind"] == "ref"
    assert arg["arguments"][0]["value"] == "owner_repository"


def test_property_value_is_not_a_dependency() -> None:
    result = _ingest("petclinic_beans.xml")
    beans = {b["name"]: b for b in _beans(result)}
    ds = beans["dataSource"]
    assert ds["dependencies"] == []
    assert ds["constructor_args"] == []


def test_property_ref_becomes_dependency() -> None:
    result = _ingest("petclinic_beans.xml")
    beans = {b["name"]: b for b in _beans(result)}
    sf = beans["sessionFactory"]
    assert len(sf["dependencies"]) == 1
    dep = sf["dependencies"][0]
    assert dep["java_name"] == "dataSource"
    assert dep["name"] == "data_source"
    assert dep["source"] == "property"


# ---------------------------------------------------------------------------
# Factory method
# ---------------------------------------------------------------------------


def test_factory_method_recorded() -> None:
    result = _ingest("petclinic_beans.xml")
    beans = {b["name"]: b for b in _beans(result)}
    sf = beans["sessionFactory"]
    assert sf["factory_methods"] == [{"name": "getObject", "arguments": []}]


def test_factory_bean_and_method_recorded() -> None:
    result = _ingest("infrastructure_beans.xml")
    # Skip the skipped anonymous bean diagnostic
    beans = {b["name"]: b for b in _beans(result)}
    pool = beans["connectionPool"]
    assert len(pool["factory_methods"]) == 1
    fm = pool["factory_methods"][0]
    assert fm["name"] == "createPool"
    assert fm["factory_bean"] == "poolFactory"


# ---------------------------------------------------------------------------
# Unsupported constructs
# ---------------------------------------------------------------------------


def test_unsupported_scope_flagged() -> None:
    result = _ingest("infrastructure_beans.xml")
    beans = {b["name"]: b for b in _beans(result)}
    request_bean = beans["requestScopedBean"]
    assert any("scope" in u for u in request_bean["unsupported"])
    assert any(d.level == "warning" for d in result.diagnostics)


def test_unsupported_parent_flagged() -> None:
    result = _ingest("infrastructure_beans.xml")
    beans = {b["name"]: b for b in _beans(result)}
    child = beans["childService"]
    assert any("parent" in u for u in child["unsupported"])


def test_bean_without_id_skipped_with_warning() -> None:
    result = _ingest("infrastructure_beans.xml")
    bean_names = {b["name"] for b in _beans(result)}
    # Three named beans; anonymous bean should be skipped
    assert "connectionPool" in bean_names
    assert "requestScopedBean" in bean_names
    assert "childService" in bean_names
    # No bean without an id
    assert len(bean_names) == 3
    assert any("no id or name" in d.message for d in result.diagnostics)


# ---------------------------------------------------------------------------
# Aliases (name attribute splitting + top-level <alias> elements)
# ---------------------------------------------------------------------------


def test_name_attribute_comma_list_splits_aliases(tmp_path: Path) -> None:
    # <bean name="repo, repositoryAlias" ...> should yield canonical "repo" and
    # alias "repositoryAlias", so a <constructor-arg ref="repositoryAlias"/> resolves.
    xml = (
        '<?xml version="1.0"?>\n'
        '<beans xmlns="http://www.springframework.org/schema/beans">\n'
        '    <bean name="repo, repositoryAlias" class="com.example.Repo"/>\n'
        "</beans>\n"
    )
    path = tmp_path / "alias_name.xml"
    path.write_text(xml, encoding="utf-8")

    result = ingest_spring_xml_files([path])
    assert result.diagnostics == []
    beans = {b["name"]: b for b in _beans(result)}
    assert "repo" in beans
    repo = beans["repo"]
    assert repo["aliases"] == ["repositoryAlias"]


def test_id_with_name_attribute_treats_name_as_aliases(tmp_path: Path) -> None:
    xml = (
        '<?xml version="1.0"?>\n'
        '<beans xmlns="http://www.springframework.org/schema/beans">\n'
        '    <bean id="ownerRepo" name="repo,repoAlias" class="com.example.Repo"/>\n'
        "</beans>\n"
    )
    path = tmp_path / "id_name.xml"
    path.write_text(xml, encoding="utf-8")

    result = ingest_spring_xml_files([path])
    beans = {b["name"]: b for b in _beans(result)}
    assert "ownerRepo" in beans
    assert set(beans["ownerRepo"]["aliases"]) == {"repo", "repoAlias"}


def test_toplevel_alias_element_injected_into_bean(tmp_path: Path) -> None:
    xml = (
        '<?xml version="1.0"?>\n'
        '<beans xmlns="http://www.springframework.org/schema/beans">\n'
        '    <bean id="ownerService" class="com.example.OwnerService"/>\n'
        '    <alias name="ownerService" alias="svc"/>\n'
        "</beans>\n"
    )
    path = tmp_path / "alias_elem.xml"
    path.write_text(xml, encoding="utf-8")

    result = ingest_spring_xml_files([path])
    assert result.diagnostics == []
    beans = {b["name"]: b for b in _beans(result)}
    assert "svc" in beans["ownerService"]["aliases"]


def test_alias_resolves_dependency_in_validation(tmp_path: Path) -> None:
    """A <constructor-arg ref="repositoryAlias"/> resolves when the provider has that alias."""
    import json

    translated_root = tmp_path / "translated"
    translated_root.mkdir()

    java_sidecar = {
        "schema_version": 1,
        "source": "AppConfig.java",
        "output": str(translated_root / "app_config.py"),
        "elements": [
            {
                "plugin": "spring-wiring",
                "kind": "method",
                "java_name": "ownerService",
                "python_name": "owner_service",
                "annotations": [],
                "metadata": {
                    "spring": {
                        "profile_version": 1,
                        "bean": {
                            "name": "ownerService",
                            "java_name": "ownerService",
                            "python_name": "owner_service",
                            "java_type": "OwnerService",
                            "python_type": "OwnerService",
                            "source_location": {
                                "line": 5,
                                "column": 4,
                                "end_line": 7,
                                "end_column": 5,
                            },
                            "dependencies": [
                                {
                                    "name": "repository_alias",
                                    "java_name": "repositoryAlias",
                                    "type": "Repo",
                                    "java_type": "Repo",
                                    "source": "parameter",
                                }
                            ],
                            "constructor_args": [],
                            "factory_methods": [],
                            "qualifier": None,
                            "primary": False,
                            "lazy": None,
                            "init_method": "",
                            "destroy_method": "",
                            "aliases": [],
                            "unsupported": [],
                        },
                    }
                },
            }
        ],
    }
    (translated_root / "app_config.wiring.json").write_text(
        json.dumps(java_sidecar), encoding="utf-8"
    )

    xml_content = (
        '<?xml version="1.0"?>\n'
        '<beans xmlns="http://www.springframework.org/schema/beans">\n'
        '    <bean name="repo, repositoryAlias" class="com.example.Repo"/>\n'
        "</beans>\n"
    )
    xml_path = tmp_path / "beans.xml"
    xml_path.write_text(xml_content, encoding="utf-8")
    xml_result = ingest_spring_xml_files([xml_path])
    (translated_root / "beans.wiring.json").write_text(
        xml_result.sidecars[0].model_dump_json(indent=2), encoding="utf-8"
    )

    from j2py.wire.loader import load_wiring_sidecars

    load_result = load_wiring_sidecars(translated_root)
    context = ValidationContext(
        translated_root=translated_root,
        wiring_dir=tmp_path / "wiring",
        sidecars=load_result.sidecars,
    )
    findings = SpringBeanDefinitionCheck().run(context)

    assert findings == [], f"alias 'repositoryAlias' should satisfy dependency; got: {findings}"


# ---------------------------------------------------------------------------
# Profile warnings
# ---------------------------------------------------------------------------


def test_root_beans_with_profile_emits_warning(tmp_path: Path) -> None:
    xml = (
        '<?xml version="1.0"?>\n'
        '<beans xmlns="http://www.springframework.org/schema/beans" profile="prod">\n'
        '    <bean id="prodBean" class="com.example.ProdBean"/>\n'
        "</beans>\n"
    )
    path = tmp_path / "profile_root.xml"
    path.write_text(xml, encoding="utf-8")

    result = ingest_spring_xml_files([path])
    # Beans are still ingested (best-effort) but a warning is emitted
    bean_names = {b["name"] for b in _beans(result)}
    assert "prodBean" in bean_names
    assert any("profile" in d.message and d.level == "warning" for d in result.diagnostics)


def test_nested_beans_element_emits_warning_not_silent_skip(tmp_path: Path) -> None:
    xml = (
        '<?xml version="1.0"?>\n'
        '<beans xmlns="http://www.springframework.org/schema/beans">\n'
        '    <bean id="mainBean" class="com.example.MainBean"/>\n'
        '    <beans profile="dev">\n'
        '        <bean id="devOnlyBean" class="com.example.DevBean"/>\n'
        "    </beans>\n"
        "</beans>\n"
    )
    path = tmp_path / "nested_beans.xml"
    path.write_text(xml, encoding="utf-8")

    result = ingest_spring_xml_files([path])
    bean_names = {b["name"] for b in _beans(result)}
    # Top-level mainBean is ingested; devOnlyBean inside nested <beans> is not
    assert "mainBean" in bean_names
    assert "devOnlyBean" not in bean_names
    # Must warn, not silently skip
    assert any("Nested <beans>" in d.message and d.level == "warning" for d in result.diagnostics)


# ---------------------------------------------------------------------------
# Source location (best-effort line numbers)
# ---------------------------------------------------------------------------


def test_source_location_has_line_number() -> None:
    result = _ingest("petclinic_beans.xml")
    beans = _beans(result)
    for bean in beans:
        loc = bean["source_location"]
        assert isinstance(loc["line"], int), f"Expected int line for {bean['name']}, got {loc}"
        assert loc["line"] > 0


def test_bean_line_numbers_are_ordered() -> None:
    result = _ingest("petclinic_beans.xml")
    beans = _beans(result)
    lines = [b["source_location"]["line"] for b in beans]
    assert lines == sorted(lines), "Beans should appear in file order"


# ---------------------------------------------------------------------------
# <import resource="..."> resolution
# ---------------------------------------------------------------------------


def test_import_follows_relative_file() -> None:
    result = ingest_spring_xml_files([FIXTURES / "root_beans.xml"], resolve_imports=True)
    # Should produce two sidecars: root_beans.xml + imported_beans.xml
    assert len(result.sidecars) == 2
    all_bean_names = {b["name"] for b in _beans(result)}
    assert "mailSender" in all_bean_names
    assert "emailService" in all_bean_names
    assert result.diagnostics == []


def test_import_not_followed_when_disabled() -> None:
    result = ingest_spring_xml_files([FIXTURES / "root_beans.xml"], resolve_imports=False)
    assert len(result.sidecars) == 1
    all_bean_names = {b["name"] for b in _beans(result)}
    assert "emailService" not in all_bean_names


def test_classpath_import_emits_warning_not_error() -> None:
    # Build a minimal XML with a classpath: import inline via tmp_path
    import tempfile

    xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">
    <import resource="classpath:security-config.xml"/>
    <bean id="myBean" class="com.example.MyBean"/>
</beans>
"""
    with tempfile.NamedTemporaryFile(suffix=".xml", mode="w", delete=False) as f:
        f.write(xml)
        tmp = Path(f.name)
    try:
        result = ingest_spring_xml_files([tmp], resolve_imports=True)
        assert any(d.level == "warning" for d in result.diagnostics)
        assert not any(d.level == "error" for d in result.diagnostics)
        beans_found = {b["name"] for b in _beans(result)}
        assert "myBean" in beans_found
    finally:
        tmp.unlink()


def test_classpath_import_not_followed_even_when_sibling_file_exists(tmp_path: Path) -> None:
    # Regression: a classpath: import must never be silently resolved to a
    # sibling file that happens to share the name. Only one sidecar (the root)
    # should be produced, and a warning emitted.
    sibling = tmp_path / "security-config.xml"
    sibling.write_text(
        '<?xml version="1.0"?>\n'
        '<beans xmlns="http://www.springframework.org/schema/beans">\n'
        '    <bean id="secretBean" class="com.example.SecretBean"/>\n'
        "</beans>\n",
        encoding="utf-8",
    )
    root = tmp_path / "app.xml"
    root.write_text(
        '<?xml version="1.0"?>\n'
        '<beans xmlns="http://www.springframework.org/schema/beans">\n'
        '    <import resource="classpath:security-config.xml"/>\n'
        '    <bean id="myBean" class="com.example.MyBean"/>\n'
        "</beans>\n",
        encoding="utf-8",
    )

    result = ingest_spring_xml_files([root], resolve_imports=True)

    assert len(result.sidecars) == 1, "classpath import must not be followed to a sibling file"
    bean_names = {b["name"] for b in _beans(result)}
    assert "secretBean" not in bean_names
    assert "myBean" in bean_names
    assert any(d.level == "warning" and "classpath" in d.message for d in result.diagnostics)


# ---------------------------------------------------------------------------
# Bare XML (no namespace)
# ---------------------------------------------------------------------------


def test_bare_xml_without_namespace_is_parsed() -> None:
    import tempfile

    xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<beans>
    <bean id="simpleBean" class="com.example.Simple">
        <constructor-arg ref="otherBean"/>
    </bean>
    <bean id="otherBean" class="com.example.Other"/>
</beans>
"""
    with tempfile.NamedTemporaryFile(suffix=".xml", mode="w", delete=False) as f:
        f.write(xml)
        tmp = Path(f.name)
    try:
        result = ingest_spring_xml_files([tmp])
        assert result.diagnostics == []
        beans = {b["name"]: b for b in _beans(result)}
        assert "simpleBean" in beans
        assert "otherBean" in beans
        assert beans["simpleBean"]["dependencies"][0]["java_name"] == "otherBean"
    finally:
        tmp.unlink()


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_parse_error_produces_error_diagnostic() -> None:
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".xml", mode="w", delete=False) as f:
        f.write("<beans><bean id=")  # truncated — deliberately malformed
        tmp = Path(f.name)
    try:
        result = ingest_spring_xml_files([tmp])
        assert any(d.level == "error" for d in result.diagnostics)
        assert result.sidecars == []
    finally:
        tmp.unlink()


def test_missing_file_produces_error_diagnostic() -> None:
    result = ingest_spring_xml_files([Path("/does/not/exist/beans.xml")])
    assert any(d.level == "error" for d in result.diagnostics)
    assert result.sidecars == []


# ---------------------------------------------------------------------------
# Integration with SpringBeanDefinitionCheck
# ---------------------------------------------------------------------------


def test_xml_beans_resolve_against_java_beans_in_validation(tmp_path: Path) -> None:
    """Beans defined in XML should satisfy dependency references from Java @Bean sidecars."""
    import json

    translated_root = tmp_path / "translated"
    translated_root.mkdir()

    # Write a Java @Bean sidecar whose dependency is satisfied by the XML sidecar.
    java_sidecar = {
        "schema_version": 1,
        "source": "AppConfig.java",
        "output": str(translated_root / "app_config.py"),
        "elements": [
            {
                "plugin": "spring-wiring",
                "kind": "method",
                "java_name": "ownerService",
                "python_name": "owner_service",
                "annotations": [],
                "metadata": {
                    "spring": {
                        "profile_version": 1,
                        "bean": {
                            "name": "ownerService",
                            "java_name": "ownerService",
                            "python_name": "owner_service",
                            "java_type": "OwnerService",
                            "python_type": "OwnerService",
                            "source_location": {
                                "line": 10,
                                "column": 4,
                                "end_line": 12,
                                "end_column": 5,
                            },
                            "dependencies": [
                                {
                                    "name": "owner_repository",
                                    "java_name": "ownerRepository",
                                    "type": "OwnerRepository",
                                    "java_type": "OwnerRepository",
                                    "source": "parameter",
                                },
                            ],
                            "constructor_args": [],
                            "factory_methods": [],
                            "qualifier": None,
                            "primary": True,
                            "lazy": None,
                            "init_method": "",
                            "destroy_method": "",
                            "unsupported": [],
                        },
                    },
                },
            },
        ],
    }
    (translated_root / "app_config.wiring.json").write_text(
        json.dumps(java_sidecar), encoding="utf-8"
    )

    # Ingest XML that defines the dependency.
    xml_content = """\
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans">
    <bean id="ownerRepository" class="com.example.OwnerRepository"/>
</beans>
"""
    xml_path = tmp_path / "beans.xml"
    xml_path.write_text(xml_content, encoding="utf-8")
    xml_result = ingest_spring_xml_files([xml_path])
    assert not any(d.level == "error" for d in xml_result.diagnostics)

    # Also write the XML sidecar to translated_root so load_wiring_sidecars picks it up.
    (translated_root / "beans.wiring.json").write_text(
        xml_result.sidecars[0].model_dump_json(indent=2), encoding="utf-8"
    )

    from j2py.wire.loader import load_wiring_sidecars

    load_result = load_wiring_sidecars(translated_root)
    context = ValidationContext(
        translated_root=translated_root,
        wiring_dir=tmp_path / "wiring",
        sidecars=load_result.sidecars,
    )
    findings = SpringBeanDefinitionCheck().run(context)

    assert findings == [], (
        f"XML-provided bean 'ownerRepository' should satisfy dependency; got: {findings}"
    )
