"""Tests for the top-level translation pipeline."""

import ast
from pathlib import Path

import j2py.llm.client as llm_client
from j2py.config.loader import ConfigLoader
from j2py.pipeline import translate_directory, translate_file

FIXTURES = Path(__file__).parent / "fixtures"
CFG = ConfigLoader().add_defaults().build()


def test_translate_file_no_llm_preserves_full_confidence_fixture() -> None:
    result = translate_file(FIXTURES / "java" / "HelloWorld.java", cfg=CFG, use_llm=False)

    assert not result.used_llm
    assert result.confidence == 1.0
    assert result.python_source == (FIXTURES / "python" / "HelloWorld.py").read_text()
    ast.parse(result.python_source)


def test_translate_file_no_llm_returns_partial_confidence_fixture() -> None:
    result = translate_file(FIXTURES / "java" / "Fields.java", cfg=CFG, use_llm=False)

    assert not result.used_llm
    assert result.confidence < 1.0
    assert "TODO(j2py): verify default value for field enabled" in result.python_source
    assert result.python_source == (FIXTURES / "python" / "Fields.py").read_text()
    ast.parse(result.python_source)


def test_translate_file_uses_llm_when_rule_coverage_is_partial(monkeypatch) -> None:
    def fake_translate_with_llm(
        *,
        java_source: str,
        partial_python: str,
        model: str,
    ) -> str:
        assert "public class Fields" in java_source
        assert "TODO(j2py): verify default value for field enabled" in partial_python
        assert model == "claude-test"
        return "class Fields:\n    pass\n"

    monkeypatch.setattr(llm_client, "translate_with_llm", fake_translate_with_llm)

    result = translate_file(
        FIXTURES / "java" / "Fields.java",
        cfg=CFG,
        use_llm=True,
        model="claude-test",
    )

    assert result.used_llm
    assert result.confidence < 1.0
    assert result.python_source == "class Fields:\n    pass\n"


def test_translate_directory_uses_dependency_order_and_package_paths(tmp_path: Path) -> None:
    source = tmp_path / "src"
    output = tmp_path / "out"
    source.mkdir()
    (source / "Child.java").write_text(
        """
        package com.example;
        import com.example.Base;
        public class Child extends Base {}
        """,
    )
    (source / "Base.java").write_text("package com.example; public class Base {}")

    result = translate_directory(source, output, cfg=CFG, use_llm=False)

    assert [path.name for path in result.order] == ["Base.java", "Child.java"]
    assert [file.output_path for file in result.files] == [
        output / "com" / "example" / "Base.py",
        output / "com" / "example" / "Child.py",
    ]


def test_translate_directory_surfaces_cycle_warnings(tmp_path: Path) -> None:
    source = tmp_path / "src"
    output = tmp_path / "out"
    source.mkdir()
    (source / "A.java").write_text("package com.example; public class A extends B {}")
    (source / "B.java").write_text("package com.example; public class B extends A {}")

    result = translate_directory(source, output, cfg=CFG, use_llm=False)

    assert sorted(path.name for path in result.order) == ["A.java", "B.java"]
    assert result.warnings
    assert "Circular dependencies" in result.warnings[0]
