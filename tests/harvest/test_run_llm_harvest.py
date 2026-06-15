"""Tests for batch LLM harvest runner helpers and CLI."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

import scripts.harvest.run_llm_harvest as runner
from j2py.config.loader import ConfigLoader
from j2py.pipeline import TranslationResult
from scripts.harvest import run_llm_harvest as harvest


def test_run_llm_harvest_passes_selected_provider_and_model(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "Probe.java"
    source.write_text("public class Probe {}", encoding="utf-8")
    observed: dict[str, object] = {}

    def fake_translate_file(path: Path, **kwargs: object) -> TranslationResult:
        observed["path"] = path
        observed.update(kwargs)
        return TranslationResult(
            source_path=path,
            python_source="class Probe:\n    pass\n",
            confidence=1.0,
            used_llm=False,
        )

    monkeypatch.setenv("J2PY_LLM_HARVEST", "1")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(
        runner,
        "HARVEST_PRESETS",
        {"local": (source,)},
    )
    monkeypatch.setattr(runner, "translate_file", fake_translate_file)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_llm_harvest.py",
            "--preset",
            "local",
            "--llm-provider",
            "gemini",
            "--model",
            "gemini-test",
        ],
    )

    assert runner.main() == 0
    assert observed["path"] == source
    assert observed["cfg"] == ConfigLoader().add_defaults().build()
    assert observed["use_llm"] is True
    assert observed["llm_provider"] == "gemini"
    assert observed["model"] == "gemini-test"
    assert observed["validate"] is True


def test_is_temp_harvest_path_detects_pytest_dirs() -> None:
    assert harvest.is_temp_harvest_path(Path("/tmp/pytest-of-user/pytest-1/test_x/Main.java"))
    assert harvest.is_temp_harvest_path(
        Path("/var/folders/xx/pytest-of-user/pytest-0/Foo.java"),
    )
    assert not harvest.is_temp_harvest_path(
        Path("/Users/me/j2py/tests/fixtures/llm/AssertProbe.java"),
    )


def test_load_paths_from_file_skips_comments_and_blanks(tmp_path: Path) -> None:
    queue = tmp_path / "queue.txt"
    queue.write_text(
        "# header\n\n/abs/A.java\n  /abs/B.java  \n# tail\n",
        encoding="utf-8",
    )
    assert harvest.load_paths_from_file(queue) == [Path("/abs/A.java"), Path("/abs/B.java")]


def test_is_package_info_path() -> None:
    assert harvest.is_package_info_path(Path("/foo/bar/package-info.java"))
    assert not harvest.is_package_info_path(Path("/foo/bar/AotDetector.java"))


def test_select_paths_skips_package_info_when_requested() -> None:
    paths = [
        Path("/good/AotDetector.java"),
        Path("/noise/package-info.java"),
        Path("/good/Assert.java"),
    ]
    assert harvest.select_paths(
        paths,
        offset=0,
        limit=0,
        skip_temp_paths=False,
        skip_package_info=True,
    ) == [Path("/good/AotDetector.java"), Path("/good/Assert.java")]


def test_select_paths_applies_offset_limit_and_temp_filter() -> None:
    paths = [
        Path("/good/One.java"),
        Path("/var/folders/xx/pytest-of-u/pytest-0/Bad.java"),
        Path("/good/Two.java"),
        Path("/good/Three.java"),
    ]
    selected = harvest.select_paths(
        paths,
        offset=0,
        limit=2,
        skip_temp_paths=True,
        skip_package_info=False,
    )
    assert selected == [Path("/good/One.java"), Path("/good/Two.java")]

    assert (
        harvest.select_paths(
            paths,
            offset=1,
            limit=0,
            skip_temp_paths=False,
            skip_package_info=False,
        )
        == paths[1:]
    )


def test_select_paths_rejects_negative_offset() -> None:
    with pytest.raises(ValueError, match="offset"):
        harvest.select_paths(
            [],
            offset=-1,
            limit=0,
            skip_temp_paths=False,
            skip_package_info=False,
        )


def test_is_gemini_quota_error_detects_client_error() -> None:
    class Fake429(Exception):
        status_code = 429

    assert harvest.is_gemini_quota_error(Fake429("RESOURCE_EXHAUSTED daily"))
    assert not harvest.is_gemini_quota_error(ValueError("nope"))


def test_is_gemini_auth_error_detects_unauthenticated() -> None:
    class Fake401(Exception):
        status_code = 401

    assert harvest.is_gemini_auth_error(Fake401("401 UNAUTHENTICATED"))
    assert harvest.is_gemini_auth_error(ValueError("ACCESS_TOKEN_TYPE_UNSUPPORTED"))
    assert not harvest.is_gemini_auth_error(ValueError("nope"))


def test_run_harvest_exits_cleanly_on_gemini_quota(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from unittest.mock import Mock

    from tenacity import RetryError

    source = tmp_path / "a.java"
    source.write_text("class A {}", encoding="utf-8")

    class Fake429(Exception):
        status_code = 429

    attempt = Mock()
    attempt.exception.return_value = Fake429("429 RESOURCE_EXHAUSTED quota")

    def boom(*args: object, **kwargs: object) -> object:
        raise RetryError(attempt)

    monkeypatch.setattr(harvest, "translate_file", boom)

    with pytest.raises(SystemExit) as exc:
        harvest.run_harvest(
            [source],
            provider="gemini",
            model=None,
            validate=True,
            sleep_seconds=0.0,
        )
    assert exc.value.code == 3


def test_run_harvest_forwards_provider_and_sleeps_after_llm(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sleeps: list[float] = []
    observed: list[dict[str, object]] = []
    first = tmp_path / "a.java"
    second = tmp_path / "b.java"
    first.write_text("class A {}", encoding="utf-8")
    second.write_text("class B {}", encoding="utf-8")

    def fake_translate_file(path: Path, **kwargs: object) -> object:
        observed.append({"path": path, **kwargs})

        class Result:
            used_llm = True
            confidence = 0.5

        return Result()

    monkeypatch.setattr(harvest, "translate_file", fake_translate_file)
    monkeypatch.setattr(harvest.time, "sleep", lambda seconds: sleeps.append(seconds))

    used, skipped = harvest.run_harvest(
        [first, second],
        provider="gemini",
        model=None,
        validate=True,
        sleep_seconds=6.0,
    )

    assert used == 2
    assert skipped == 0
    assert len(observed) == 2
    assert observed[0]["llm_provider"] == "gemini"
    assert observed[1]["llm_provider"] == "gemini"
    assert sleeps == [6.0]


def test_run_harvest_skips_sleep_when_rule_layer_complete(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sleeps: list[float] = []
    source = tmp_path / "a.java"
    source.write_text("class A {}", encoding="utf-8")

    def fake_translate_file(path: Path, **kwargs: object) -> object:
        class Result:
            used_llm = False
            confidence = 1.0

        return Result()

    monkeypatch.setattr(harvest, "translate_file", fake_translate_file)
    monkeypatch.setattr(harvest.time, "sleep", lambda seconds: sleeps.append(seconds))

    used, skipped = harvest.run_harvest(
        [source],
        provider="gemini",
        model=None,
        validate=True,
        sleep_seconds=6.0,
    )

    assert used == 0
    assert skipped == 1
    assert sleeps == []


def test_require_api_key_exits_when_gemini_key_missing(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(harvest, "load_repo_dotenv", lambda: None)
    with pytest.raises(SystemExit) as exc:
        harvest.require_api_key("gemini")
    assert exc.value.code == 2
    assert "GEMINI_API_KEY" in capsys.readouterr().err


def test_require_api_key_exits_when_gemini_key_is_oauth_token(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "ya29.oauth-token")
    monkeypatch.setattr(harvest, "load_repo_dotenv", lambda: None)
    with pytest.raises(SystemExit) as exc:
        harvest.require_api_key("gemini")
    assert exc.value.code == 2
    assert "OAuth access token" in capsys.readouterr().err
