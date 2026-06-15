"""Pinned external Java corpora for j2py rule-layer scoreboards.

Each preset defines a git remote/ref, source modules, sampling parameters, and baseline
path. Use with ``translate_spring_sample.py --preset <name>``.

External git checkouts live under ``<J2PY_CORPUS_ROOT or repo root>/.corpus/<name>/``.
Set ``J2PY_CORPUS_ROOT`` to the main j2py checkout when working in a git worktree so
agents and scripts reuse one shared clone directory.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_CORPUS = REPO_ROOT / "tests" / "fixtures" / "corpus"

# One preset per unique checkout_dir — used by ``make corpus-clone-all``.
CLONE_PRESET_NAMES: tuple[str, ...] = (
    "spring-dense",
    "guava-dense",
    "commons-lang-dense",
    "jackson-dense",
    "caffeine-dense",
)


def corpus_checkout_root() -> Path:
    """Return the ``.corpus/`` directory that holds external Java checkouts."""
    override = os.environ.get("J2PY_CORPUS_ROOT", "").strip()
    if override:
        path = Path(override).expanduser()
        root = path if path.is_absolute() else (REPO_ROOT / path).resolve()
    else:
        root = REPO_ROOT
    return root / ".corpus"


@dataclass(frozen=True)
class CorpusPreset:
    name: str
    description: str
    remote: str
    ref: str
    checkout_dir: str
    modules: tuple[str, ...]
    baseline: Path
    limit: int = 100
    strategy: str = "density"
    max_loc: int = 250
    min_constructs: int = 5
    include_constructs: bool = False
    include_tests: bool = False
    exclude_paths: tuple[str, ...] = ()

    @property
    def repo_path(self) -> Path:
        return corpus_checkout_root() / self.checkout_dir

    @property
    def json_out(self) -> Path:
        return REPO_ROOT / "corpus-reports" / f"{self.name}.json"

    @property
    def csv_out(self) -> Path:
        return REPO_ROOT / "corpus-reports" / f"{self.name}.csv"


def _preset(
    name: str,
    description: str,
    remote: str,
    ref: str,
    checkout_dir: str,
    modules: tuple[str, ...],
    baseline_name: str,
    **kwargs: object,
) -> CorpusPreset:
    return CorpusPreset(
        name=name,
        description=description,
        remote=remote,
        ref=ref,
        checkout_dir=checkout_dir,
        modules=modules,
        baseline=FIXTURES_CORPUS / baseline_name,
        **kwargs,  # type: ignore[arg-type]
    )


PRESETS: dict[str, CorpusPreset] = {
    preset.name: preset
    for preset in (
        _preset(
            "spring-dense",
            "Preferred dense Spring sample plus curated construct fixtures",
            remote="https://github.com/spring-projects/spring-framework.git",
            ref="0c60266986197a191ff33eb498ebc8bac3dc933f",
            checkout_dir="spring-framework",
            modules=(
                "spring-core/src/main/java",
                "spring-beans/src/main/java",
            ),
            baseline_name="spring-dense-baseline.json",
            include_constructs=True,
        ),
        _preset(
            "spring-broad",
            "Exploratory spring-context sample plus construct fixtures (no committed baseline)",
            remote="https://github.com/spring-projects/spring-framework.git",
            ref="0c60266986197a191ff33eb498ebc8bac3dc933f",
            checkout_dir="spring-framework",
            modules=("spring-context/src/main/java",),
            baseline_name="spring-broad-baseline.json",
            limit=150,
            include_constructs=True,
            min_constructs=0,
        ),
        _preset(
            "spring-lexical",
            "Historical lexical Spring-only baseline (spring-core + spring-beans)",
            remote="https://github.com/spring-projects/spring-framework.git",
            ref="0c60266986197a191ff33eb498ebc8bac3dc933f",
            checkout_dir="spring-framework",
            modules=(
                "spring-core/src/main/java",
                "spring-beans/src/main/java",
            ),
            baseline_name="spring-sample-baseline.json",
            strategy="lexical",
            max_loc=0,
            min_constructs=0,
        ),
        _preset(
            "guava-dense",
            "Google Guava collect/base utilities (generics-heavy library Java)",
            remote="https://github.com/google/guava.git",
            ref="v33.4.8",
            checkout_dir="guava",
            modules=(
                "guava/src/com/google/common/collect",
                "guava/src/com/google/common/base",
            ),
            baseline_name="guava-dense-baseline.json",
            exclude_paths=(
                # tree-sitter-java ERROR on Jspecify type-use @Nullable before varargs
                # (`@Nullable Object @Nullable ... args` in lenientFormat); translation
                # still reaches full coverage but parse_ok stays false — see #160.
                "guava/src/com/google/common/base/Platform.java",
            ),
        ),
        _preset(
            "commons-lang-dense",
            "Apache Commons Lang classic utility Java without framework magic",
            remote="https://github.com/apache/commons-lang.git",
            ref="rel/commons-lang-3.17.0",
            checkout_dir="commons-lang",
            modules=("src/main/java",),
            baseline_name="commons-lang-dense-baseline.json",
        ),
        _preset(
            "jackson-dense",
            "Jackson databind annotation and bean-introspection patterns",
            remote="https://github.com/FasterXML/jackson-databind.git",
            ref="jackson-databind-2.18.2",
            checkout_dir="jackson-databind",
            modules=("src/main/java",),
            baseline_name="jackson-dense-baseline.json",
        ),
        _preset(
            "caffeine-dense",
            "Caffeine cache concurrent/lambda-heavy library Java",
            remote="https://github.com/ben-manes/caffeine.git",
            ref="v3.1.8",
            checkout_dir="caffeine",
            modules=("caffeine/src/main/java",),
            baseline_name="caffeine-dense-baseline.json",
        ),
    )
}


def get_preset(name: str) -> CorpusPreset:
    try:
        return PRESETS[name]
    except KeyError as exc:
        known = ", ".join(sorted(PRESETS))
        raise ValueError(f"Unknown corpus preset {name!r}. Known presets: {known}") from exc


def list_preset_names() -> list[str]:
    return sorted(PRESETS)


def apply_preset(
    preset: CorpusPreset,
    args: dict[str, object],
) -> dict[str, object]:
    """Fill argparse fields from a preset; explicit CLI overrides win for path/limit fields."""
    overridable = (
        "repo",
        "remote",
        "ref",
        "modules",
        "limit",
        "baseline",
        "json_out",
        "csv_out",
        "strategy",
        "max_loc",
        "min_constructs",
        "include_constructs",
        "include_tests",
        "exclude_paths",
    )
    resolved: dict[str, object] = {
        "repo": preset.repo_path,
        "remote": preset.remote,
        "ref": preset.ref,
        "modules": list(preset.modules),
        "limit": preset.limit,
        "strategy": preset.strategy,
        "max_loc": preset.max_loc,
        "min_constructs": preset.min_constructs,
        "include_constructs": preset.include_constructs,
        "include_tests": preset.include_tests,
        "exclude_paths": list(preset.exclude_paths),
        "baseline": preset.baseline,
        "json_out": preset.json_out,
        "csv_out": preset.csv_out,
        "preset": preset.name,
    }
    for key in overridable:
        value = args.get(key)
        if value is not None:
            resolved[key] = value
    return resolved
