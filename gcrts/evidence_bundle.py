"""EvidenceBundle model for the overlay engine's live test runner
(`docs/overlay_engine/PS1_OVERLAY_RUNTIME_SYSTEM_DESIGN.md` §12,
`PS1_OVERLAY_RUNTIME_REQUIREMENTS.md` VAL-005/VAL-006).

Per VAL-005, every validation result carries: runtime context,
screenshot path(s), event log, and PASS/FAIL/UNSUPPORTED. Per VAL-006,
external-host overlay success and internal-game overlay success must
stay distinguishable -- `backend` is the field that does that
(`EXTERNAL_HOST` for everything built so far; `INTERNAL_PS1` is
reserved for the internal-overlay stage, not used by any code yet).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum


class OverlayBackend(str, Enum):
    EXTERNAL_HOST = "EXTERNAL_HOST"
    INTERNAL_PS1 = "INTERNAL_PS1"


class ValidationResult(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass
class EvidenceBundle:
    scenario_name: str
    timestamp: str  # ISO 8601, UTC
    backend: OverlayBackend
    result: ValidationResult
    runtime_context: dict
    host_screenshot_path: str | None = None
    emulator_screenshot_path: str | None = None
    event_log: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "scenario_name": self.scenario_name,
            "timestamp": self.timestamp,
            "backend": self.backend.value,
            "result": self.result.value,
            "runtime_context": self.runtime_context,
            "host_screenshot_path": self.host_screenshot_path,
            "emulator_screenshot_path": self.emulator_screenshot_path,
            "event_log": list(self.event_log),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EvidenceBundle":
        return cls(
            scenario_name=d["scenario_name"],
            timestamp=d["timestamp"],
            backend=OverlayBackend(d["backend"]),
            result=ValidationResult(d["result"]),
            runtime_context=d.get("runtime_context", {}),
            host_screenshot_path=d.get("host_screenshot_path"),
            emulator_screenshot_path=d.get("emulator_screenshot_path"),
            event_log=list(d.get("event_log", [])),
            notes=d.get("notes", ""),
        )

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: str) -> "EvidenceBundle":
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))
