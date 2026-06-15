"""Behavior-equivalence tests comparing Java output with translated Python output."""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from j2py.config.loader import ConfigLoader
from j2py.pipeline import translate_directory
from j2py.translate.runtime import RUNTIME_MODULE_NAME, runtime_module_source

FIXTURES = Path(__file__).parent.parent / "fixtures" / "behavior"
CFG = ConfigLoader().add_defaults().build()

#: Per-process wall-clock cap. A corpus case that loops forever (in Java or in the
#: translated Python) must fail loudly instead of hanging the CI job indefinitely.
PROCESS_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class BehaviorCase:
    name: str
    main_class: str = "Main"
    xfail_reason: str | None = None
    process_timeout: int = field(default=PROCESS_TIMEOUT_SECONDS)

    @property
    def path(self) -> Path:
        return FIXTURES / self.name


@dataclass(frozen=True)
class ProcessResult:
    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


def _discover_cases() -> tuple[BehaviorCase, ...]:
    """Every fixtures/behavior/<name>/ directory that holds a Main.java is a case.

    Optional sidecar files in a fixture directory:
    - ``main_class.txt``: entry-point class name (default: ``Main``)
    - ``xfail.txt``: reason string — marks the case xfail(strict=True) to track known
      rule-layer bugs; the test is expected to fail until the bug is fixed
    - ``timeout_seconds.txt``: per-process timeout in seconds (default: PROCESS_TIMEOUT_SECONDS)
      — useful for infinite-loop xfail cases that would otherwise hang for 30 s each run

    New corpus cases are added by dropping a directory here — no edit to this file is required.
    """
    cases: list[BehaviorCase] = []
    for entry in sorted(FIXTURES.iterdir()):
        if not entry.is_dir() or not (entry / "Main.java").exists():
            continue
        override = entry / "main_class.txt"
        main_class = override.read_text(encoding="utf-8").strip() if override.exists() else "Main"
        xfail_file = entry / "xfail.txt"
        xfail_reason = (
            xfail_file.read_text(encoding="utf-8").strip() if xfail_file.exists() else None
        )
        timeout_file = entry / "timeout_seconds.txt"
        timeout = (
            int(timeout_file.read_text(encoding="utf-8").strip())
            if timeout_file.exists()
            else PROCESS_TIMEOUT_SECONDS
        )
        cases.append(BehaviorCase(entry.name, main_class, xfail_reason, timeout))
    return tuple(cases)


CASES = _discover_cases()


def _case_params() -> list[object]:
    """Build pytest.param entries, attaching xfail marks for known-broken cases."""
    params = []
    for case in CASES:
        marks: list[pytest.MarkDecorator] = []
        if case.xfail_reason:
            marks.append(pytest.mark.xfail(strict=True, reason=case.xfail_reason))
        params.append(pytest.param(case, id=case.name, marks=marks))
    return params


#: Floor for the curated behavior corpus. The corpus is the release gate for
#: rule-layer runtime equivalence; if it silently shrinks the gate is worthless.
MINIMUM_CORPUS_SIZE = 50


def test_behavior_corpus_meets_minimum_size() -> None:
    """Cheap guard (no JDK): the corpus must not silently lose cases.

    Runs in the normal suite so a deleted/renamed fixture fails fast even where
    the JDK-backed equivalence tests are skipped.
    """
    assert len(CASES) >= MINIMUM_CORPUS_SIZE, (
        f"behavior corpus shrank to {len(CASES)} cases (floor {MINIMUM_CORPUS_SIZE}); "
        "did a fixtures/behavior/<case>/Main.java go missing?"
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
@pytest.mark.parametrize(
    ("main_class", "expected"),
    [
        ("Main", "from Main import Main\n\nif __name__ == '__main__':\n    Main.main([])\n"),
        (
            "com.example.Main",
            (
                "from com.example.Main import Main\n\n"
                "if __name__ == '__main__':\n"
                "    Main.main([])\n"
            ),
        ),
    ],
)
def test_python_runner_uses_main_class_import_path(main_class: str, expected: str) -> None:
    assert _python_runner_source(main_class) == expected


@pytest.mark.behavior
@pytest.mark.parametrize("case", _case_params())
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
        timeout=case.process_timeout,
    )
    assert compile_result.returncode == 0, compile_result.stderr
    java_result = _run(
        ["java", "-cp", str(classes), case.main_class],
        cwd=java_work,
        timeout=case.process_timeout,
    )

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
        result.output_path.write_text(result.python_source, encoding="utf-8")
    uses_runtime = any(
        f"from {RUNTIME_MODULE_NAME} import " in result.python_source for result in translated.files
    )
    if uses_runtime:
        (python_work / f"{RUNTIME_MODULE_NAME}.py").write_text(
            runtime_module_source(),
            encoding="utf-8",
        )

    runner = python_work / "run_translated.py"
    runner.write_text(_python_runner_source(case.main_class), encoding="utf-8")
    python_result = _run(
        [sys.executable, str(runner)],
        cwd=python_work,
        timeout=case.process_timeout,
    )
    _assert_same_behavior(java=java_result, python=python_result)


def _require_java_toolchain() -> None:
    missing = [name for name in ("java", "javac") if shutil.which(name) is None]
    if missing:
        raise RuntimeError(
            "behavior tests require `java` and `javac`; missing: " + ", ".join(missing),
        )


def _run(command: list[str], *, cwd: Path, timeout: int = PROCESS_TIMEOUT_SECONDS) -> ProcessResult:
    try:
        proc = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            encoding="utf-8",
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return ProcessResult(
            command=tuple(command),
            returncode=124,
            stdout=exc.stdout or "",
            stderr=(exc.stderr or "") + f"\nTIMEOUT after {timeout}s",
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
        "=== java ===\n"
        f"java command: {' '.join(java.command)}\n"
        f"java returncode: {java.returncode}\n"
        f"--- stdout ---\n{java.stdout}"
        f"--- stderr ---\n{java.stderr}"
        "=== python ===\n"
        f"python command: {' '.join(python.command)}\n"
        f"python returncode: {python.returncode}\n"
        f"--- stdout ---\n{python.stdout}"
        f"--- stderr ---\n{python.stderr}"
    )


def _python_runner_source(main_class: str) -> str:
    module_path, _, class_name = main_class.rpartition(".")
    import_path = f"{module_path}.{class_name}" if module_path else class_name
    return (
        f"from {import_path} import {class_name}\n\n"
        "if __name__ == '__main__':\n"
        f"    {class_name}.main([])\n"
    )
