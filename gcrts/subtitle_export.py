"""Subtitle export: the first real "product access" deliverable for a
confirmed dialogue asset, deliberately scoped to text-only subtitles --
no audio recording, no injection. Builds a standard `.srt` file from a
`DialogueDatabaseEntry`'s already-real translation, using the asset's
own known `duration_seconds` for timing (a real, physically-derived
number, see `gcrts.xapack.AudioAsset`, not guessed).

Refuses to export anything without a real translation already present
(`build_subtitle_cue` raises `ValueError`) -- this module never invents
subtitle text of its own. It also never claims more confidence than the
underlying entry actually has: `subtitle_caveat` surfaces
`transcript_verified`/`translation_approved` honestly in the sidecar
metadata (see `export_subtitle_for_asset`), so a still-unverified draft
subtitle is never indistinguishable from an approved one downstream.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

from gcrts.dialogue_database import DEFAULT_DB_PATH, DialogueDatabaseEntry, get_entry


def format_srt_timestamp(seconds: float) -> str:
    """`HH:MM:SS,mmm`, the standard SubRip timestamp format."""
    if seconds < 0:
        raise ValueError(f"seconds must be >= 0, got {seconds!r}")
    total_ms = round(seconds * 1000)
    hours, rem_ms = divmod(total_ms, 3_600_000)
    minutes, rem_ms = divmod(rem_ms, 60_000)
    secs, ms = divmod(rem_ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


@dataclass
class SubtitleCue:
    index: int
    start_seconds: float
    end_seconds: float
    speaker: str | None
    text: str

    def to_srt_block(self) -> str:
        line = f"{self.speaker}: {self.text}" if self.speaker else self.text
        return (
            f"{self.index}\n"
            f"{format_srt_timestamp(self.start_seconds)} --> {format_srt_timestamp(self.end_seconds)}\n"
            f"{line}\n"
        )


def build_subtitle_cue(entry: DialogueDatabaseEntry, index: int = 1, start_seconds: float = 0.0) -> SubtitleCue:
    """One cue spanning the asset's own real `duration_seconds`, starting
    at `start_seconds` (0.0 for a standalone clip -- callers embedding
    this into a longer timeline pass the real offset instead). Raises
    `ValueError` if `entry.translation` is empty -- there is nothing
    honest to subtitle yet."""
    if not entry.translation:
        raise ValueError(f"{entry.asset_id!r} has no translation yet -- nothing to export as a subtitle.")
    return SubtitleCue(
        index=index,
        start_seconds=start_seconds,
        end_seconds=start_seconds + entry.duration_seconds,
        speaker=entry.character,
        text=entry.translation,
    )


def write_srt(cues: list[SubtitleCue], path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(cue.to_srt_block() for cue in cues))


def subtitle_caveat(entry: DialogueDatabaseEntry) -> str:
    """A plain, honest one-line summary of how settled this subtitle's
    text actually is -- never silently omitted just because it's
    inconvenient. Read by `export_subtitle_for_asset`'s sidecar, not
    embedded in the `.srt` itself (a video player has no use for it)."""
    if entry.translation_approved and entry.transcript_verified:
        return "Transcript verified and translation approved -- ready for subtitle use."
    parts = []
    if not entry.transcript_verified:
        parts.append("Japanese transcript not yet human-verified as belonging to this exact audio moment.")
    if not entry.translation_approved:
        parts.append("Translation is a draft, not yet approved.")
    return " ".join(parts) if parts else "Ready for subtitle use."


def export_subtitle_for_asset(
    asset_id: str,
    out_path: str,
    db_path: str = DEFAULT_DB_PATH,
    start_seconds: float = 0.0,
) -> str:
    """Convenience wrapper: `asset_id -> real .srt file on disk`, plus a
    JSON sidecar (`<out_path>.meta.json`) carrying the honest
    verification caveat above. Raises `KeyError` if the asset isn't in
    the database yet, `ValueError` if it has no translation."""
    entry = get_entry(asset_id, path=db_path)
    if entry is None:
        raise KeyError(f"{asset_id!r} is not in the dialogue database yet ({db_path}).")
    cue = build_subtitle_cue(entry, start_seconds=start_seconds)
    write_srt([cue], out_path)
    meta_path = out_path + ".meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "asset_id": asset_id,
                "japanese_transcript": entry.japanese_transcript,
                "transcript_verified": entry.transcript_verified,
                "translation_approved": entry.translation_approved,
                "caveat": subtitle_caveat(entry),
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    return out_path
