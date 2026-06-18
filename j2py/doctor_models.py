"""Public data models for doctor assessments."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

DOCTOR_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class DoctorAssessment:
    """JSON-serialisable project assessment."""

    payload: dict[str, Any]

    def to_json(self) -> str:
        return json.dumps(self.payload, indent=2, sort_keys=True) + "\n"


@dataclass(frozen=True)
class DoctorDiff:
    """JSON-serialisable comparison between two doctor assessments."""

    payload: dict[str, Any]

    def to_json(self) -> str:
        return json.dumps(self.payload, indent=2, sort_keys=True) + "\n"
