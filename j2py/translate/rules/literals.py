"""Literal and keyword token translations."""

from __future__ import annotations

import re

from j2py.config.loader import TranslationConfig


def translate_literal(token: str, cfg: TranslationConfig) -> str:
    """Map a Java literal token to its Python equivalent."""
    if token in cfg.literal_map:
        return cfg.literal_map[token]

    # Long suffix: 100L → 100
    if re.match(r"^\d+[Ll]$", token):
        return token[:-1]

    # Float suffix: 1.0f, 1.0F → 1.0
    if re.match(r"^[\d.]+[fF]$", token):
        return token[:-1]

    # Double suffix: 1.0d → 1.0
    if re.match(r"^[\d.]+[dD]$", token):
        return token[:-1]

    # Hex: 0xFF → same in Python
    # Binary: 0b1010 → same in Python
    # Underscore separators: 1_000_000 → same in Python

    # Char literal: 'a' → "a"
    if re.match(r"^'[^']'$", token) or re.match(r"^'\\.'$", token):
        inner = token[1:-1]
        return f'"{inner}"'

    return token
