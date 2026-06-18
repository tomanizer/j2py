"""Shared CLI configuration helpers."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

import typer

from j2py.cli.output import console

if TYPE_CHECKING:
    from j2py.config.loader import TranslationConfig

LLMProvider = Literal["anthropic", "gemini", "openai"]
LlmReviewScope = Literal["all", "warnings", "low-confidence"]


def normalize_llm_provider(value: str) -> LLMProvider:
    normalized = value.lower().replace("_", "-")
    if normalized == "openai-compatible":
        normalized = "openai"
    if normalized not in {"anthropic", "gemini", "openai"}:
        raise typer.BadParameter(
            "unsupported LLM provider; choose 'anthropic', 'gemini', or 'openai'",
            param_hint="--llm-provider",
        )
    return cast(LLMProvider, normalized)


def normalize_llm_review_scope(value: str) -> LlmReviewScope:
    normalized = value.lower().replace("_", "-")
    if normalized not in {"all", "warnings", "low-confidence"}:
        raise typer.BadParameter(
            "unsupported LLM review scope; choose 'all', 'warnings', or 'low-confidence'",
            param_hint="--llm-review-scope",
        )
    return cast(LlmReviewScope, normalized)


def resolve_llm_options(
    cfg: TranslationConfig,
    llm_provider: str | None,
    model: str | None,
) -> tuple[LLMProvider, str | None]:
    provider = (
        normalize_llm_provider(llm_provider)
        if llm_provider is not None
        else cfg.llm_provider or "anthropic"
    )
    effective_model = model if model is not None else cfg.model
    return provider, effective_model


def load_config(config: list[Path], auto_root: Path | None = None) -> TranslationConfig:
    from j2py.config.loader import ConfigError, ConfigLoader

    loader = ConfigLoader().add_defaults()
    try:
        if config:
            for c in config:
                loader.add_file(c)
        elif auto_root is not None:
            loader.add_auto_discovered(auto_root)
        return loader.build()
    except ConfigError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc
