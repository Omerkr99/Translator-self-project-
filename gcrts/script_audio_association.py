"""Script Context <-> Audio Dispatch Correlation.

Answers a question the Audio Cue Resolution Generalization milestone
(`AUDIO_CUE_RESOLUTION.md`) deliberately left open: the raw
`sound_or_voice_cue` script parameter is NOT a stable physical-source
identity (the same value, 127, has been live-observed resolving to two
different `XAPACK*.BIN` files at different real times). This module
replaces "identify audio by cue number" with "identify audio by which
exact script occurrence dispatched it" -- a `ScriptUnit` (already a
real, tested concept in `gcrts.script_unit`) plus the specific word
offset of the `sound_or_voice_cue` control code inside it.

Everything here is pure, injected-`read_memory` logic (no breakpoints --
the same discipline `gcrts.runtime_audio`/`gcrts.renderer1_runtime`
already established, for the same reason: this project's own history of
GDB breakpoint/continue hangs, and this session's own direct finding
that breakpoint overhead measurably slows the emulator's effective
timing relative to free-running polling).

Key runtime address used, live-confirmed in a prior session
(`DECODER_READ_CURSOR.md`, full breakpoint-verified trace from the
decoder's own entry to its word-consumption instruction):

    cursor_addr  = 0x800A4CEA   (global, 16-bit, WORD-index into the
                                  script buffer, not a byte offset)
    read_address = SCRIPT_BUF_ADDR + cursor * 2

The cursor always points at the NEXT word the interpreter is about to
read (or has just read) -- so "the script occurrence that owns whatever
is currently dispatched" is the most recent `sound_or_voice_cue`
control code whose own words have already been fully consumed
(`offset + words_consumed <= cursor`), not necessarily the exact current
cursor position (character codes for the text following the cue are
typically still being consumed after it).

**Word offset alone is NOT a stable identity, confirmed live this
session.** `DECODER_READ_CURSOR.md` already documented that the live
script buffer "appears to be refreshed/rewritten as the game streams
new content in, likely in chunks smaller than a whole scene" -- this
session found direct, concrete proof: three captures of the identical
save state, ~14s apart, ALL showed a `sound_or_voice_cue` occurrence at
the exact same word offset (1) with the exact same raw parameter (127),
yet the third resolved to a different physical `XAPACK*.BIN` file than
the first two, and the live script cursor itself had dropped to a LOWER
value than either earlier capture -- impossible if the interpreter were
still reading forward through the same buffer content. The buffer had
been refreshed with new (but structurally similar -- another line that
also happens to open with a sound cue at offset 1, also parameterized
127) content between captures. `buffer_fingerprint` below (a hash of the
owning unit's own decoded content, not its position) is what makes
`stable_key` actually stable across this kind of refresh.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from gcrts.live_extract import SCRIPT_BUF_ADDR
from gcrts.runtime_audio import RuntimeAudioEvent, capture_audio_event
from gcrts.script_decoder import CodeKind, ScriptCode, ScriptDocument, decode_script
from gcrts.script_unit import ScriptUnit, units_from_script_document

CURSOR_ADDR = 0x800A4CEA
SOUND_OR_VOICE_CUE_SUBTYPE = 0x0800
DEFAULT_CAPTURE_BYTES = 4096  # matches gcrts.live_extract's own default capture size


class ScriptAssociationConfidence(str, Enum):
    SCRIPT_CONTEXT_RESOLVED = "SCRIPT_CONTEXT_RESOLVED"  # a real owning ScriptUnit + control-code occurrence was found
    SCRIPT_CONTEXT_UNKNOWN = "SCRIPT_CONTEXT_UNKNOWN"  # script buffer/cursor were readable, but no owning occurrence could be determined
    UNAVAILABLE = "UNAVAILABLE"  # script buffer or cursor could not be read at all


@dataclass
class ScriptAudioAssociation:
    association_id: str
    script_source: str  # matches gcrts.script_unit.ScriptUnit.source ("live_ram" today)
    script_unit_id: str | None
    script_unit_start: int | None
    script_unit_end: int | None
    script_cursor: int | None
    control_code_offset: int | None  # word offset of the owning sound_or_voice_cue occurrence
    control_code_type: int | None  # subtype -- always 0x0800 when resolved, kept explicit for future control codes
    control_code_raw_low_byte: int | None  # the control WORD's own low byte (raw & 0xff) -- see gcrts.audio_context: this, not raw_parameter, is the real per-line selector, confirmed live this session
    raw_parameter: int | None  # the SEPARATE inline word (historically, but wrongly, treated as "the sound index" -- see gcrts.audio_context's module docstring)
    dialogue_text: str | None  # owning unit's original_text -- human-readable context, not an identity field
    buffer_fingerprint: str | None  # short hash of the owning unit's own decoded content -- see module docstring
    audio_event: dict | None  # RuntimeAudioEvent.to_dict(), or None if no live event was supplied/found
    confidence: ScriptAssociationConfidence

    @property
    def stable_key(self) -> str | None:
        """The project identity this milestone set out to build:
        disc/script provenance + ScriptUnit + command offset + content
        fingerprint -- NOT a raw RAM address (overlays/buffers can move)
        and NOT the raw cue parameter alone (proven unstable) and NOT
        word offset alone either (proven unstable across buffer
        refreshes -- see module docstring). None when script context
        wasn't resolved -- never fabricated from a RAM address as a
        fallback."""
        if self.script_unit_id is None or self.control_code_offset is None:
            return None
        return f"{self.script_source}/{self.script_unit_id}/offset_{self.control_code_offset:#x}/{self.buffer_fingerprint}"

    def to_dict(self) -> dict:
        return {
            "association_id": self.association_id,
            "script_source": self.script_source,
            "script_unit_id": self.script_unit_id,
            "script_unit_start": self.script_unit_start,
            "script_unit_end": self.script_unit_end,
            "script_cursor": self.script_cursor,
            "control_code_offset": self.control_code_offset,
            "control_code_type": self.control_code_type,
            "control_code_raw_low_byte": self.control_code_raw_low_byte,
            "raw_parameter": self.raw_parameter,
            "dialogue_text": self.dialogue_text,
            "buffer_fingerprint": self.buffer_fingerprint,
            "audio_event": self.audio_event,
            "confidence": self.confidence.value,
            "stable_key": self.stable_key,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ScriptAudioAssociation":
        return cls(
            association_id=d["association_id"],
            script_source=d.get("script_source", "live_ram"),
            script_unit_id=d.get("script_unit_id"),
            script_unit_start=d.get("script_unit_start"),
            script_unit_end=d.get("script_unit_end"),
            script_cursor=d.get("script_cursor"),
            control_code_offset=d.get("control_code_offset"),
            control_code_type=d.get("control_code_type"),
            control_code_raw_low_byte=d.get("control_code_raw_low_byte"),
            raw_parameter=d.get("raw_parameter"),
            dialogue_text=d.get("dialogue_text"),
            buffer_fingerprint=d.get("buffer_fingerprint"),
            audio_event=d.get("audio_event"),
            confidence=ScriptAssociationConfidence(d.get("confidence", "UNAVAILABLE")),
        )


def _fingerprint_unit(unit: ScriptUnit) -> str:
    """Short, deterministic hash of a unit's own decoded content
    (raw_codes -- the actual script words, not its position). Two units
    with identical content hash the same regardless of where they sit in
    the buffer; two genuinely different lines that happen to share a
    word offset (see module docstring) hash differently."""
    return hashlib.sha1(repr(unit.raw_codes).encode("utf-8")).hexdigest()[:12]


def find_owning_sound_cue(doc: ScriptDocument, cursor: int) -> ScriptCode | None:
    """The most recently fully-consumed sound_or_voice_cue occurrence at
    or before `cursor` -- i.e. the one the interpreter has already acted
    on, which is what "currently dispatched audio" is attributable to.
    Pure, no I/O -- testable against a hand-built ScriptDocument."""
    candidates = [
        c
        for c in doc.codes
        if c.kind == CodeKind.CONTROL
        and c.subtype == SOUND_OR_VOICE_CUE_SUBTYPE
        and c.offset + c.words_consumed <= cursor
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda c: c.offset)


def find_owning_unit(units: list[ScriptUnit], offset: int) -> ScriptUnit | None:
    """Which ScriptUnit's [start, end) range contains `offset`. Pure, no
    I/O. Units are gapless and non-overlapping by construction
    (gcrts.script_unit's own documented invariant), so at most one match
    is ever possible."""
    for unit in units:
        if unit.unit_start_offset <= offset < unit.unit_end_offset:
            return unit
    return None


def build_script_audio_association(
    cursor: int | None,
    doc: ScriptDocument | None,
    units: list[ScriptUnit],
    audio_event: RuntimeAudioEvent | None,
    association_id: str,
    script_source: str = "live_ram",
) -> ScriptAudioAssociation:
    """Pure composition -- no I/O. Callers that have live memory access
    should use `capture_script_audio_association` instead; this exists
    separately so the actual association LOGIC (finding the owning
    occurrence and unit, deciding confidence) is testable with
    hand-built fixtures, matching this project's established pattern
    for every other live-capture module."""
    if cursor is None or doc is None:
        return ScriptAudioAssociation(
            association_id=association_id,
            script_source=script_source,
            script_unit_id=None,
            script_unit_start=None,
            script_unit_end=None,
            script_cursor=cursor,
            control_code_offset=None,
            control_code_type=None,
            control_code_raw_low_byte=None,
            raw_parameter=None,
            dialogue_text=None,
            buffer_fingerprint=None,
            audio_event=audio_event.to_dict() if audio_event is not None else None,
            confidence=ScriptAssociationConfidence.UNAVAILABLE,
        )

    owning_cue = find_owning_sound_cue(doc, cursor)
    owning_unit = find_owning_unit(units, owning_cue.offset) if owning_cue is not None else None

    if owning_cue is None or owning_unit is None:
        return ScriptAudioAssociation(
            association_id=association_id,
            script_source=script_source,
            script_unit_id=None,
            script_unit_start=None,
            script_unit_end=None,
            script_cursor=cursor,
            control_code_offset=owning_cue.offset if owning_cue is not None else None,
            control_code_type=owning_cue.subtype if owning_cue is not None else None,
            control_code_raw_low_byte=(owning_cue.raw & 0xFF) if owning_cue is not None else None,
            raw_parameter=owning_cue.param if owning_cue is not None else None,
            dialogue_text=None,
            buffer_fingerprint=None,
            audio_event=audio_event.to_dict() if audio_event is not None else None,
            confidence=ScriptAssociationConfidence.SCRIPT_CONTEXT_UNKNOWN,
        )

    return ScriptAudioAssociation(
        association_id=association_id,
        script_source=script_source,
        script_unit_id=owning_unit.id,
        script_unit_start=owning_unit.unit_start_offset,
        script_unit_end=owning_unit.unit_end_offset,
        script_cursor=cursor,
        control_code_offset=owning_cue.offset,
        control_code_type=owning_cue.subtype,
        control_code_raw_low_byte=owning_cue.raw & 0xFF,
        raw_parameter=owning_cue.param,
        dialogue_text=owning_unit.original_text,
        buffer_fingerprint=_fingerprint_unit(owning_unit),
        audio_event=audio_event.to_dict() if audio_event is not None else None,
        confidence=ScriptAssociationConfidence.SCRIPT_CONTEXT_RESOLVED,
    )


def capture_script_audio_association(
    read_memory: Callable[[int, int], bytes | None],
    audio_event: RuntimeAudioEvent | None = None,
    association_id: str = "current",
    scene_id: str = "live",
    capture_bytes: int = DEFAULT_CAPTURE_BYTES,
) -> ScriptAudioAssociation:
    """One-shot snapshot read (no breakpoints) -- reads the cursor and the
    live script buffer, decodes and segments it, and associates whatever
    `audio_event` the caller already captured this cycle (avoiding a
    second, possibly inconsistent RAM fetch -- pass one in if you have
    it; if not, this captures a fresh one itself via
    `gcrts.runtime_audio.capture_audio_event`)."""
    cursor_bytes = read_memory(CURSOR_ADDR, 2)
    cursor = int.from_bytes(cursor_bytes, "little") if cursor_bytes else None

    raw = read_memory(SCRIPT_BUF_ADDR, capture_bytes)
    doc = decode_script(raw) if raw is not None else None
    units = units_from_script_document(doc, scene_id, source="live_ram", base_ram_address=SCRIPT_BUF_ADDR) if doc is not None else []

    if audio_event is None:
        audio_event = capture_audio_event(read_memory, event_id=association_id)

    return build_script_audio_association(cursor, doc, units, audio_event, association_id)
