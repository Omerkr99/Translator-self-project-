"""Dialogue Asset Database -- the unified workbench record for one
audio asset's whole translation/dub lifecycle. Phase 1 of the
project's own prioritized "Fandub Management Layer" roadmap: turns the
research already done (source identity, physical format, semantic
classification, human-confirmed labels, Fandub templates) into one
real, queryable system instead of scattered files a person has to
cross-reference by hand.

This module does not replace any of the underlying stores -- it reads
from `gcrts.xapack`/`gcrts.audio_semantic`/`gcrts.semantic_label_store`/
`gcrts.audio_replacement` and combines them into one record with its
own explicit workflow status and evidence list, then persists that
combined view separately (`audio_export/dialogue_database.json`, same
gitignore/regeneration discipline as everything else under
`audio_export/`).

## Workflow status is derived, never asserted

`compute_workflow_status()` looks at what fields are ACTUALLY filled
in (transcript present? translation present? recording present?) and
derives the furthest-along status consistent with that -- it never
jumps ahead of real, observable progress. A caller cannot mark
something `RECORDED` just by wanting to; the status reflects what data
genuinely exists on the entry.

## Evidence is additive, never fabricated

`evidence` is a plain list of short, factual strings describing real
things that were actually done (a live capture, a decoder verification,
a listening session) -- per this project's own standing rule against
inventing confidence. Nothing in this module auto-generates evidence
text; callers append real observations.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from gcrts.audio_replacement import FandubEntry, load_fandub_template
from gcrts.audio_semantic import SemanticType, VerificationSource
from gcrts.semantic_label_store import get_label
from gcrts.xapack import AudioAsset

DEFAULT_DB_PATH = os.path.join("audio_export", "dialogue_database.json")


class DialogueWorkflowStatus(str, Enum):
    DETECTED = "DETECTED"  # the asset exists and is known, nothing else yet
    TRANSCRIPT_ADDED = "TRANSCRIPT_ADDED"
    TRANSCRIPT_VERIFIED = "TRANSCRIPT_VERIFIED"  # a human confirmed the transcript belongs to THIS asset specifically
    TRANSLATION_DRAFT = "TRANSLATION_DRAFT"
    TRANSLATION_APPROVED = "TRANSLATION_APPROVED"
    READY_FOR_RECORDING = "READY_FOR_RECORDING"
    RECORDED = "RECORDED"
    AUDIO_VALIDATED = "AUDIO_VALIDATED"
    READY_FOR_INJECTION = "READY_FOR_INJECTION"


@dataclass
class DialogueDatabaseEntry:
    asset_id: str
    pack_path: str
    channel_number: int
    duration_seconds: float
    sample_rate_hz: int
    channels: int

    semantic_type: SemanticType = SemanticType.UNKNOWN
    semantic_confirmed: bool = False  # True only for USER_LISTENING/RUNTIME_EVIDENCE, never a bare heuristic guess
    semantic_verification_source: VerificationSource = VerificationSource.UNVERIFIED

    character: str | None = None
    japanese_transcript: str | None = None
    transcript_verified: bool = False  # a human confirmed the transcript belongs to THIS specific asset, not just a nearby screen
    translation: str | None = None
    translation_approved: bool = False

    workflow_status: DialogueWorkflowStatus = DialogueWorkflowStatus.DETECTED
    evidence: list[str] = field(default_factory=list)
    scene_notes: str | None = None
    notes: str = ""
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "asset_id": self.asset_id,
            "pack_path": self.pack_path,
            "channel_number": self.channel_number,
            "duration_seconds": self.duration_seconds,
            "sample_rate_hz": self.sample_rate_hz,
            "channels": self.channels,
            "semantic_type": self.semantic_type.value,
            "semantic_confirmed": self.semantic_confirmed,
            "semantic_verification_source": self.semantic_verification_source.value,
            "character": self.character,
            "japanese_transcript": self.japanese_transcript,
            "transcript_verified": self.transcript_verified,
            "translation": self.translation,
            "translation_approved": self.translation_approved,
            "workflow_status": self.workflow_status.value,
            "evidence": list(self.evidence),
            "scene_notes": self.scene_notes,
            "notes": self.notes,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DialogueDatabaseEntry":
        return cls(
            asset_id=d["asset_id"],
            pack_path=d["pack_path"],
            channel_number=d["channel_number"],
            duration_seconds=d["duration_seconds"],
            sample_rate_hz=d["sample_rate_hz"],
            channels=d["channels"],
            semantic_type=SemanticType(d.get("semantic_type", "UNKNOWN")),
            semantic_confirmed=d.get("semantic_confirmed", False),
            semantic_verification_source=VerificationSource(d.get("semantic_verification_source", "UNVERIFIED")),
            character=d.get("character"),
            japanese_transcript=d.get("japanese_transcript"),
            transcript_verified=d.get("transcript_verified", False),
            translation=d.get("translation"),
            translation_approved=d.get("translation_approved", False),
            workflow_status=DialogueWorkflowStatus(d.get("workflow_status", "DETECTED")),
            evidence=list(d.get("evidence", [])),
            scene_notes=d.get("scene_notes"),
            notes=d.get("notes", ""),
            updated_at=d.get("updated_at", ""),
        )


def compute_workflow_status(entry: DialogueDatabaseEntry) -> DialogueWorkflowStatus:
    """Derives the furthest-along status consistent with what's
    ACTUALLY filled in on `entry` -- never asserts progress that
    isn't reflected in real data. Recording/validation/injection
    status still requires a caller to explicitly set those fields
    (this module has no recording/injection capability itself, per
    the project's own standing scope boundary)."""
    if entry.workflow_status in (
        DialogueWorkflowStatus.RECORDED,
        DialogueWorkflowStatus.AUDIO_VALIDATED,
        DialogueWorkflowStatus.READY_FOR_INJECTION,
    ):
        return entry.workflow_status  # these require an explicit external action this module can't infer

    if entry.translation_approved and entry.transcript_verified:
        return DialogueWorkflowStatus.READY_FOR_RECORDING
    if entry.translation_approved:
        return DialogueWorkflowStatus.TRANSLATION_APPROVED
    if entry.translation:
        return DialogueWorkflowStatus.TRANSLATION_DRAFT
    if entry.transcript_verified:
        return DialogueWorkflowStatus.TRANSCRIPT_VERIFIED
    if entry.japanese_transcript:
        return DialogueWorkflowStatus.TRANSCRIPT_ADDED
    return DialogueWorkflowStatus.DETECTED


def build_entry_from_asset(
    asset: AudioAsset,
    label_store_path: str | None = None,
    fandub_template_path: str | None = None,
) -> DialogueDatabaseEntry:
    """Combines the real `AudioAsset`, its confirmed semantic label (if
    any), and its Fandub template (if one has been scaffolded) into
    one entry. Never fabricates a transcript/translation/character
    that isn't already present in one of those real sources."""
    from gcrts.semantic_label_store import DEFAULT_STORE_PATH

    label = get_label(asset.asset_id, path=label_store_path or DEFAULT_STORE_PATH)
    semantic_type = label.semantic_type if label else SemanticType.UNKNOWN
    confirmed = label is not None and label.verification_source in (
        VerificationSource.USER_LISTENING,
        VerificationSource.RUNTIME_EVIDENCE,
    )
    verification_source = label.verification_source if label else VerificationSource.UNVERIFIED

    character = None
    transcript = None
    translation = None
    translation_approved = False
    if fandub_template_path and os.path.exists(fandub_template_path):
        template: FandubEntry = load_fandub_template(fandub_template_path)
        character = template.speaker
        transcript = template.japanese_transcript
        translation = template.translation

    entry = DialogueDatabaseEntry(
        asset_id=asset.asset_id,
        pack_path=asset.pack_path,
        channel_number=asset.channel_number,
        duration_seconds=asset.duration_seconds,
        sample_rate_hz=asset.format.sample_rate_hz,
        channels=asset.format.channel_count,
        semantic_type=semantic_type,
        semantic_confirmed=confirmed,
        semantic_verification_source=verification_source,
        character=character,
        japanese_transcript=transcript,
        translation=translation,
        translation_approved=translation_approved,
    )
    entry.workflow_status = compute_workflow_status(entry)
    return entry


def load_database(path: str = DEFAULT_DB_PATH) -> dict[str, DialogueDatabaseEntry]:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return {aid: DialogueDatabaseEntry.from_dict(d) for aid, d in raw.items()}


def _write_database(db: dict[str, DialogueDatabaseEntry], path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({aid: e.to_dict() for aid, e in db.items()}, f, indent=2, ensure_ascii=False)


def save_entry(entry: DialogueDatabaseEntry, path: str = DEFAULT_DB_PATH) -> DialogueDatabaseEntry:
    entry.workflow_status = compute_workflow_status(entry)
    entry.updated_at = datetime.now(timezone.utc).isoformat()
    db = load_database(path)
    db[entry.asset_id] = entry
    _write_database(db, path)
    return entry


def get_entry(asset_id: str, path: str = DEFAULT_DB_PATH) -> DialogueDatabaseEntry | None:
    return load_database(path).get(asset_id)


def add_evidence(asset_id: str, evidence_line: str, path: str = DEFAULT_DB_PATH) -> DialogueDatabaseEntry:
    """Appends one real, factual evidence line to an existing entry.
    Raises KeyError if the entry doesn't exist yet -- callers must
    `save_entry` (or `build_entry_from_asset` + `save_entry`) first."""
    db = load_database(path)
    if asset_id not in db:
        raise KeyError(f"{asset_id!r} is not in the database yet -- save_entry() first.")
    db[asset_id].evidence.append(evidence_line)
    db[asset_id].updated_at = datetime.now(timezone.utc).isoformat()
    _write_database(db, path)
    return db[asset_id]


def list_by_status(status: DialogueWorkflowStatus, path: str = DEFAULT_DB_PATH) -> list[DialogueDatabaseEntry]:
    return [e for e in load_database(path).values() if e.workflow_status == status]


def list_by_semantic_type(semantic_type: SemanticType, path: str = DEFAULT_DB_PATH) -> list[DialogueDatabaseEntry]:
    return [e for e in load_database(path).values() if e.semantic_type == semantic_type]


def dashboard_summary(path: str = DEFAULT_DB_PATH) -> dict:
    """A real, computed status dashboard -- counts only, never
    presented as more complete than the data actually is."""
    db = load_database(path)
    by_status: dict[str, int] = {}
    by_semantic: dict[str, int] = {}
    confirmed_count = 0
    for entry in db.values():
        by_status[entry.workflow_status.value] = by_status.get(entry.workflow_status.value, 0) + 1
        by_semantic[entry.semantic_type.value] = by_semantic.get(entry.semantic_type.value, 0) + 1
        if entry.semantic_confirmed:
            confirmed_count += 1
    return {
        "total_assets": len(db),
        "confirmed_semantic_labels": confirmed_count,
        "by_status": by_status,
        "by_semantic_type": by_semantic,
    }
