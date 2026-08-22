"""Live Audio Inspector: the "NOW PLAYING" bridge from a live
`RuntimeAudioEvent` (`gcrts.runtime_audio`) through the already-working
LBA resolver (`gcrts.audio_asset_resolver`) to the unified Dialogue
Asset Database (`gcrts.dialogue_database`). This is the second of the
three next-priority items named in the project's own Fandub Pipeline
roadmap: a display layer over infrastructure that already exists,
adding no new resolution logic of its own.

Read-mostly, with one deliberate, narrow write: the first time a real
LBA resolves to an `AudioAsset` this project has never seen before, a
plain `DETECTED` entry is registered for it (`build_entry_from_asset` +
`save_entry`) -- this is the honest, literal meaning of "detected," not
a guess at anything semantic. An asset that already has a database
entry is only ever read here, never re-saved -- `build_entry_from_asset`
would silently drop any `evidence`/`scene_notes`/`notes` a human has
since added by hand (those aren't sourced from the label store or a
Fandub template, so rebuilding fresh would lose them), so this module
must never overwrite an existing entry.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable

from gcrts.audio_asset_resolver import AudioAssetResolution, ResolutionConfidence, resolve_audio_asset
from gcrts.dialogue_database import (
    DEFAULT_DB_PATH,
    DialogueDatabaseEntry,
    build_entry_from_asset,
    get_entry,
    save_entry,
)
from gcrts.runtime_audio import AudioLifecycleState, RuntimeAudioEvent


def fandub_template_path_for_asset(asset_id: str) -> str:
    """Same layout `gcrts.audio_replacement.scaffold_fandub_project`
    already writes to (`audio_export/fandub/<ASSET_ID with ':' -> '_'>/
    template.json`) -- so an asset that already has a scaffolded
    template gets its transcript/translation reflected here too,
    without this module needing its own separate convention."""
    return os.path.join("audio_export", "fandub", asset_id.replace(":", "_"), "template.json")


@dataclass
class LiveAudioInspection:
    lifecycle_state: AudioLifecycleState
    resolution_confidence: ResolutionConfidence
    asset_id: str | None
    newly_registered: bool
    database_entry: DialogueDatabaseEntry | None

    def to_dict(self) -> dict:
        return {
            "lifecycle_state": self.lifecycle_state.value,
            "resolution_confidence": self.resolution_confidence.value,
            "asset_id": self.asset_id,
            "newly_registered": self.newly_registered,
            "database_entry": self.database_entry.to_dict() if self.database_entry is not None else None,
        }


def inspect_live_audio(
    audio_event: RuntimeAudioEvent | None,
    disc_bytes: bytes | None,
    db_path: str = DEFAULT_DB_PATH,
    label_store_path: str | None = None,
    auto_register: bool = True,
    resolve_fn: Callable[[bytes, int], AudioAssetResolution] = resolve_audio_asset,
) -> LiveAudioInspection | None:
    """Returns `None` only when there is nothing to inspect at all (no
    audio event captured this poll, or no disc bytes available to
    resolve an LBA against) -- never fabricates a resolution. When an
    event exists but its `start_lba` doesn't resolve to a real
    `AudioAsset` (e.g. `PACK_ONLY`/`UNRESOLVED`), still returns a real
    `LiveAudioInspection` with `asset_id=None`, since the lifecycle
    state and resolution attempt are themselves real, reportable facts."""
    if audio_event is None or disc_bytes is None or audio_event.start_lba is None:
        return None

    resolution = resolve_fn(disc_bytes, audio_event.start_lba)
    if resolution.asset is None:
        return LiveAudioInspection(
            lifecycle_state=audio_event.state,
            resolution_confidence=resolution.confidence,
            asset_id=None,
            newly_registered=False,
            database_entry=None,
        )

    asset_id = resolution.asset.asset_id
    entry = get_entry(asset_id, path=db_path)
    newly_registered = False
    if entry is None and auto_register:
        entry = build_entry_from_asset(
            resolution.asset,
            label_store_path=label_store_path,
            fandub_template_path=fandub_template_path_for_asset(asset_id),
        )
        entry = save_entry(entry, path=db_path)
        newly_registered = True

    return LiveAudioInspection(
        lifecycle_state=audio_event.state,
        resolution_confidence=resolution.confidence,
        asset_id=asset_id,
        newly_registered=newly_registered,
        database_entry=entry,
    )


def format_now_playing(inspection: LiveAudioInspection | None) -> str:
    """One human-readable status line -- the actual "NOW PLAYING:
    <asset_id>" the roadmap asked for, kept as a plain function so both
    a GUI panel and a CLI/log driver can reuse the exact same text."""
    if inspection is None:
        return "NOW PLAYING: (no live audio data)"
    if inspection.asset_id is None:
        return f"NOW PLAYING: (unresolved, {inspection.resolution_confidence.value}) [{inspection.lifecycle_state.value}]"
    entry = inspection.database_entry
    tag = " (new)" if inspection.newly_registered else ""
    if entry is None:
        return f"NOW PLAYING: {inspection.asset_id}{tag} [{inspection.lifecycle_state.value}]"
    semantic = entry.semantic_type.value if entry.semantic_confirmed else f"{entry.semantic_type.value}?"
    return (
        f"NOW PLAYING: {inspection.asset_id}{tag} [{inspection.lifecycle_state.value}] "
        f"{semantic} -- {entry.workflow_status.value}"
    )
