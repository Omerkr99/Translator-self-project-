"""Human-in-the-loop semantic label persistence.

The explicit design point: once a human confirms an `AudioAsset`'s
semantic role (by listening, or by real runtime evidence), that label
is authoritative and MUST be persisted -- this project should never
have to re-guess the same asset's role in a future session. Manual
listening is not a fallback for when automation fails; it is the
primary verification method for this whole semantic layer (see
`gcrts.audio_semantic`'s own module docstring), and its results are
first-class, durable project data, not a one-off chat answer.

Storage is a single, human-readable JSON file
(`audio_export/semantic_labels.json` by default) -- not a database,
since the expected scale (dozens to low hundreds of confirmed labels)
does not need one, and a plain JSON file is trivial to inspect, diff,
and back up alongside the rest of this project's evidence trail.

Overwriting an existing confirmed label requires the explicit
`allow_overwrite=True` -- this is deliberate friction, matching the
standing rule that a confirmed label is never silently reclassified
without contradictory evidence.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone

from gcrts.audio_semantic import SemanticType, VerificationSource

DEFAULT_STORE_PATH = os.path.join("audio_export", "semantic_labels.json")


@dataclass(frozen=True)
class VerifiedLabel:
    asset_id: str
    semantic_type: SemanticType
    verification_source: VerificationSource
    notes: str
    verified_at: str  # ISO-8601 UTC timestamp

    def to_dict(self) -> dict:
        return {
            "asset_id": self.asset_id,
            "semantic_type": self.semantic_type.value,
            "verification_source": self.verification_source.value,
            "notes": self.notes,
            "verified_at": self.verified_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "VerifiedLabel":
        return cls(
            asset_id=d["asset_id"],
            semantic_type=SemanticType(d["semantic_type"]),
            verification_source=VerificationSource(d["verification_source"]),
            notes=d.get("notes", ""),
            verified_at=d.get("verified_at", ""),
        )


def load_labels(path: str = DEFAULT_STORE_PATH) -> dict[str, VerifiedLabel]:
    """Never raises for a missing file -- an empty store is the normal
    starting state, not an error."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return {aid: VerifiedLabel.from_dict(d) for aid, d in raw.items()}


def _write_labels(labels: dict[str, VerifiedLabel], path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({aid: label.to_dict() for aid, label in labels.items()}, f, indent=2, ensure_ascii=False)


def save_label(
    asset_id: str,
    semantic_type: SemanticType,
    verification_source: VerificationSource,
    notes: str = "",
    path: str = DEFAULT_STORE_PATH,
    allow_overwrite: bool = False,
) -> VerifiedLabel:
    """Persist a human-confirmed (or runtime-evidence-confirmed) label.
    Raises ValueError if `asset_id` already has a confirmed label and
    `allow_overwrite` is not explicitly set -- deliberate friction, see
    module docstring."""
    labels = load_labels(path)
    if asset_id in labels and not allow_overwrite:
        raise ValueError(
            f"{asset_id!r} already has a confirmed label "
            f"({labels[asset_id].semantic_type.value}, {labels[asset_id].verification_source.value}) -- "
            "pass allow_overwrite=True with real contradictory evidence to replace it."
        )
    label = VerifiedLabel(
        asset_id=asset_id,
        semantic_type=semantic_type,
        verification_source=verification_source,
        notes=notes,
        verified_at=datetime.now(timezone.utc).isoformat(),
    )
    labels[asset_id] = label
    _write_labels(labels, path)
    return label


def get_label(asset_id: str, path: str = DEFAULT_STORE_PATH) -> VerifiedLabel | None:
    return load_labels(path).get(asset_id)


def is_confirmed(asset_id: str, path: str = DEFAULT_STORE_PATH) -> bool:
    label = get_label(asset_id, path)
    return label is not None and label.verification_source in (
        VerificationSource.USER_LISTENING,
        VerificationSource.RUNTIME_EVIDENCE,
    )
