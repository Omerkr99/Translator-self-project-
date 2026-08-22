"""Fandub Replacement Template -- data model and validation-preview
rules only. This module deliberately implements NONE of: audio
re-injection, disc rebuild, encoding, resampling, or a recording UI.
It exists so that once an `AudioAsset` is confirmed as real dialogue
(`gcrts.semantic_label_store.is_confirmed`), a human translator/dub
workflow has a concrete, structured starting point instead of loose
notes -- matching the desired eventual pipeline:

```
Dialogue line -> Play Japanese -> Read translation -> Record/import dub
  -> compare duration -> validate -> encode -> replace
```

Only the first five steps are prepared here (a template + validation
preview); "encode" and "replace" are explicitly out of scope until the
earlier steps are solid across many real, confirmed assets.

## Why gated on a CONFIRMED semantic label

`scaffold_fandub_project` refuses to build a project for an asset that
isn't already confirmed dialogue (`gcrts.semantic_label_store`) --
per this project's own standing rule against building product-facing
scaffolding on top of an unverified `HEURISTIC` guess. A candidate
that turns out to be music/ambience should never accidentally grow a
translation template.

## Why validation is rules-only, not automatic correction

`validate_replacement` reports facts (duration difference, sample rate
mismatch, clipping, excess silence) -- it never resamples, re-encodes,
or otherwise modifies a replacement recording. Per the original
milestone's own instruction: "Do not resample or encode replacement
audio in this milestone." A translator/dub workflow needs to see the
real numbers and decide, not have them silently normalized away.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from gcrts.semantic_label_store import is_confirmed
from gcrts.xapack import AudioAsset


class ReplacementValidationStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"  # no replacement recording supplied yet
    DURATION_MISMATCH = "DURATION_MISMATCH"
    FORMAT_MISMATCH = "FORMAT_MISMATCH"  # sample rate and/or channel count differs from the original
    CLIPPING_DETECTED = "CLIPPING_DETECTED"
    SILENCE_DETECTED = "SILENCE_DETECTED"  # the replacement is mostly/entirely silent -- likely a bad import
    READY_FOR_ENCODE = "READY_FOR_ENCODE"  # all checks passed -- still requires human APPROVED before anything downstream
    APPROVED = "APPROVED"  # a human explicitly signed off, separate from READY_FOR_ENCODE's automated checks


@dataclass
class FandubEntry:
    """One line's worth of original-audio + translation + replacement
    bookkeeping. Every `original_*` field is filled in once, from a
    real `AudioAsset` (see `create_fandub_template`), and never edited
    afterward by this module -- only the translation/replacement
    fields are meant to be hand-edited by a translator/dub workflow."""

    original_asset_id: str
    original_pack_path: str
    original_channel_number: int
    original_duration_seconds: float
    original_sample_rate_hz: int
    original_channels: int

    # Filled in by a human/translation workflow -- None until then.
    japanese_transcript: str | None = None
    translation: str | None = None
    speaker: str | None = None
    caption_notes: str | None = None

    # Filled in once a replacement recording exists.
    replacement_file: str | None = None
    replacement_actor: str | None = None
    replacement_language: str = "en"
    replacement_duration_seconds: float | None = None
    replacement_sample_rate_hz: int | None = None
    replacement_channels: int | None = None

    validation_status: ReplacementValidationStatus = ReplacementValidationStatus.NOT_STARTED
    validation_notes: str = ""
    notes: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "original_asset_id": self.original_asset_id,
            "original_pack_path": self.original_pack_path,
            "original_channel_number": self.original_channel_number,
            "original_duration_seconds": self.original_duration_seconds,
            "original_sample_rate_hz": self.original_sample_rate_hz,
            "original_channels": self.original_channels,
            "japanese_transcript": self.japanese_transcript,
            "translation": self.translation,
            "speaker": self.speaker,
            "caption_notes": self.caption_notes,
            "replacement_file": self.replacement_file,
            "replacement_actor": self.replacement_actor,
            "replacement_language": self.replacement_language,
            "replacement_duration_seconds": self.replacement_duration_seconds,
            "replacement_sample_rate_hz": self.replacement_sample_rate_hz,
            "replacement_channels": self.replacement_channels,
            "validation_status": self.validation_status.value,
            "validation_notes": self.validation_notes,
            "notes": self.notes,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FandubEntry":
        return cls(
            original_asset_id=d["original_asset_id"],
            original_pack_path=d["original_pack_path"],
            original_channel_number=d["original_channel_number"],
            original_duration_seconds=d["original_duration_seconds"],
            original_sample_rate_hz=d["original_sample_rate_hz"],
            original_channels=d["original_channels"],
            japanese_transcript=d.get("japanese_transcript"),
            translation=d.get("translation"),
            speaker=d.get("speaker"),
            caption_notes=d.get("caption_notes"),
            replacement_file=d.get("replacement_file"),
            replacement_actor=d.get("replacement_actor"),
            replacement_language=d.get("replacement_language", "en"),
            replacement_duration_seconds=d.get("replacement_duration_seconds"),
            replacement_sample_rate_hz=d.get("replacement_sample_rate_hz"),
            replacement_channels=d.get("replacement_channels"),
            validation_status=ReplacementValidationStatus(d.get("validation_status", "NOT_STARTED")),
            validation_notes=d.get("validation_notes", ""),
            notes=d.get("notes", ""),
            created_at=d.get("created_at", ""),
        )


def create_fandub_template(asset: AudioAsset, language: str = "en") -> FandubEntry:
    """Pre-fills only what's already known and real (from the
    `AudioAsset` itself) -- every translation/replacement field starts
    empty, never fabricated."""
    return FandubEntry(
        original_asset_id=asset.asset_id,
        original_pack_path=asset.pack_path,
        original_channel_number=asset.channel_number,
        original_duration_seconds=asset.duration_seconds,
        original_sample_rate_hz=asset.format.sample_rate_hz,
        original_channels=asset.format.channel_count,
        replacement_language=language,
    )


# Validation thresholds -- generous, since this is a preview for a
# human to react to, not an automatic gate.
_DURATION_MISMATCH_RATIO = 0.15  # >15% shorter/longer than the original flags for review
_CLIPPING_SAMPLE_THRESHOLD = 32760  # near int16 max -- real clipping, not just a loud peak
_SILENCE_RATIO_THRESHOLD = 0.9  # >90% nominally-silent samples suggests a bad/empty import


def validate_replacement(
    entry: FandubEntry,
    replacement_duration_seconds: float,
    replacement_sample_rate_hz: int,
    replacement_channels: int,
    peak_amplitude: int | None = None,
    silence_ratio: float | None = None,
) -> FandubEntry:
    """Rules-only validation preview -- never resamples, re-encodes, or
    otherwise modifies the replacement audio (per this module's own
    docstring). Returns a NEW `FandubEntry` with `replacement_*` and
    `validation_status`/`validation_notes` populated; the input entry
    is not mutated."""
    issues: list[str] = []

    if replacement_sample_rate_hz != entry.original_sample_rate_hz or replacement_channels != entry.original_channels:
        issues.append(
            f"format mismatch: replacement is {replacement_sample_rate_hz}Hz/{replacement_channels}ch, "
            f"original is {entry.original_sample_rate_hz}Hz/{entry.original_channels}ch"
        )
        status = ReplacementValidationStatus.FORMAT_MISMATCH
    elif peak_amplitude is not None and abs(peak_amplitude) >= _CLIPPING_SAMPLE_THRESHOLD:
        issues.append(f"clipping detected: peak amplitude {peak_amplitude}")
        status = ReplacementValidationStatus.CLIPPING_DETECTED
    elif silence_ratio is not None and silence_ratio >= _SILENCE_RATIO_THRESHOLD:
        issues.append(f"mostly silent: {silence_ratio:.0%} of samples near-zero")
        status = ReplacementValidationStatus.SILENCE_DETECTED
    elif entry.original_duration_seconds > 0 and (
        abs(replacement_duration_seconds - entry.original_duration_seconds) / entry.original_duration_seconds
        > _DURATION_MISMATCH_RATIO
    ):
        diff = replacement_duration_seconds - entry.original_duration_seconds
        issues.append(f"duration differs by {diff:+.2f}s ({entry.original_duration_seconds:.2f}s -> {replacement_duration_seconds:.2f}s)")
        status = ReplacementValidationStatus.DURATION_MISMATCH
    else:
        status = ReplacementValidationStatus.READY_FOR_ENCODE

    return FandubEntry.from_dict({
        **entry.to_dict(),
        "replacement_duration_seconds": replacement_duration_seconds,
        "replacement_sample_rate_hz": replacement_sample_rate_hz,
        "replacement_channels": replacement_channels,
        "validation_status": status.value,
        "validation_notes": "; ".join(issues) or "all checks passed",
    })


def save_fandub_template(entry: FandubEntry, path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entry.to_dict(), f, indent=2, ensure_ascii=False)


def load_fandub_template(path: str) -> FandubEntry:
    with open(path, encoding="utf-8") as f:
        return FandubEntry.from_dict(json.load(f))


def scaffold_fandub_project(asset: AudioAsset, out_dir: str, language: str = "en", label_store_path: str | None = None) -> str:
    """Creates `out_dir/template.json` -- the starting point for a
    translator/dub workflow. Refuses (raises ValueError) unless the
    asset already has a CONFIRMED semantic label (real human listening
    or runtime evidence, never a bare heuristic guess) -- per this
    module's own docstring. Returns the template's path. Does not
    write any audio file itself; pair this with
    `gcrts.audio_asset_resolver.export_audio_asset_wav` for the
    original reference audio if needed."""
    from gcrts.semantic_label_store import DEFAULT_STORE_PATH

    path_to_check = label_store_path if label_store_path is not None else DEFAULT_STORE_PATH
    if not is_confirmed(asset.asset_id, path=path_to_check):
        raise ValueError(
            f"{asset.asset_id!r} has no confirmed semantic label yet -- "
            "listen and call gcrts.semantic_label_store.save_label first. "
            "Refusing to scaffold a Fandub project on an unverified candidate."
        )
    template = create_fandub_template(asset, language=language)
    template_path = os.path.join(out_dir, "template.json")
    save_fandub_template(template, template_path)
    return template_path
