"""Behavior-equivalence tests comparing Java output with translated Python output."""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from j2py.config.loader import ConfigLoader
from j2py.pipeline import translate_directory

FIXTURES = Path(__file__).parent.parent / "fixtures" / "behavior"
CFG = ConfigLoader().add_defaults().build()


@dataclass(frozen=True)
class BehaviorCase:
    name: str
    main_class: str = "Main"

    @property
    def path(self) -> Path:
        return FIXTURES / self.name


@dataclass(frozen=True)
class ProcessResult:
    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


CASES = (
    BehaviorCase("hello_print"),
    BehaviorCase("fields_methods"),
    BehaviorCase("if_else_arithmetic"),
    BehaviorCase("loops_sum"),
    BehaviorCase("enhanced_for_list"),
)


@pytest.mark.behavior
def test_behavior_toolchain_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)

    with pytest.raises(RuntimeError, match="require `java` and `javac`"):
        _require_java_toolchain()


@pytest.mark.behavior
def test_assert_same_behavior_reports_stdout_mismatch() -> None:
    java = ProcessResult(("java", "Main"), 0, "java\n", "")
    python = ProcessResult(("python", "run_translated.py"), 0, "python\n", "")

    with pytest.raises(AssertionError, match="stdout mismatch"):
        _assert_same_behavior(java=java, python=python)


@pytest.mark.behavior
def test_assert_same_behavior_reports_returncode_mismatch() -> None:
    java = ProcessResult(("java", "Main"), 0, "", "")
    python = ProcessResult(("python", "run_translated.py"), 1, "", "boom\n")

    with pytest.raises(AssertionError, match="return code mismatch"):
        _assert_same_behavior(java=java, python=python)


@pytest.mark.behavior
@pytest.mark.parametrize("case", CASES, ids=[case.name for case in CASES])
def test_translated_python_matches_java_behavior(case: BehaviorCase, tmp_path: Path) -> None:
    _require_java_toolchain()

    java_work = tmp_path / "java"
    classes = tmp_path / "classes"
    python_work = tmp_path / "python"
    shutil.copytree(case.path, java_work)
    classes.mkdir()
    python_work.mkdir()

    java_files = sorted(java_work.rglob("*.java"))
    compile_result = _run(
        ["javac", "-d", str(classes), *(str(path) for path in java_files)],
        cwd=java_work,
    )
    assert compile_result.returncode == 0, compile_result.stderr
    java_result = _run(["java", "-cp", str(classes), case.main_class], cwd=java_work)

    translated = translate_directory(
        java_work,
        python_work,
        cfg=CFG,
        use_llm=False,
        validate=False,
    )
    for result in translated.files:
        assert result.output_path is not None
        result.output_path.parent.mkdir(parents=True, exist_ok=True)
        result.output_path.write_text(result.python_source)

    runner = python_work / "run_translated.py"
    runner.write_text(
        "from Main import Main\n\n"
        "if __name__ == '__main__':\n"
        "    Main.main([])\n",
    )
    python_result = _run([sys.executable, str(runner)], cwd=python_work)
    _assert_same_behavior(java=java_result, python=python_result)


def _require_java_toolchain() -> None:
    missing = [name for name in ("java", "javac") if shutil.which(name) is None]
    if missing:
        raise RuntimeError(
            "behavior tests require `java` and `javac`; missing: " + ", ".join(missing),
        )


def _run(command: list[str], *, cwd: Path) -> ProcessResult:
    proc = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return ProcessResult(
        command=tuple(command),
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )


def _assert_same_behavior(*, java: ProcessResult, python: ProcessResult) -> None:
    assert python.returncode == java.returncode, _format_mismatch(
        "return code mismatch",
        java=java,
        python=python,
    )
    assert python.stdout == java.stdout, _format_mismatch(
        "stdout mismatch",
        java=java,
        python=python,
    )
    assert python.stderr == java.stderr, _format_mismatch(
        "stderr mismatch",
        java=java,
        python=python,
    )


def _format_mismatch(reason: str, *, java: ProcessResult, python: ProcessResult) -> str:
    return (
        f"{reason}\n"
        f"java command: {' '.join(java.command)}\n"
        f"java returncode: {java.returncode}\n"
        f"java stdout:\n{java.stdout}"
        f"java stderr:\n{java.stderr}"
        f"python command: {' '.join(python.command)}\n"
        f"python returncode: {python.returncode}\n"
        f"python stdout:\n{python.stdout}"
        f"python stderr:\n{python.stderr}"
    )
