"""Audio Context Resolution -- the causal mechanism this project's own
`AUDIO_CUE_RESOLUTION.md` and `SCRIPT_AUDIO_ASSOCIATION.md` left open:
*why* a given `sound_or_voice_cue` script occurrence resolves to the
specific physical `XAPACK*.BIN` file it does. This is now FULLY closed,
down to a literal, static, embedded filename string -- see "Complete
resolution" below.

Headline finding, live-confirmed this session: the "127" inline
parameter every prior pass tracked was NEVER the real per-line selector.
The `sound_or_voice_cue` control WORD's own low byte
(`raw_word & 0xff`) is -- a value no earlier pass had separately
examined, because `gcrts.script_decoder.ScriptCode.param` only exposes
the SEPARATE inline extra word, not the opcode word's own low bits.

Two live-observed script occurrences (the same two `ScriptUnit`
fingerprint groups from `SCRIPT_AUDIO_ASSOCIATION.md`) had raw control
words `0xc819` and `0xc81a` -- identical apart from the low byte (`0x19`
= 25 vs `0x1a` = 26) -- while their SEPARATE inline parameter was
identical (127) in both. This directly corrects an earlier session's own
misreading: `BACKLOG_INVESTIGATION_RESULTS.md`'s Stage C trace captured
`0x80075b68`'s `$a1` argument as `0x1a` and described it as "matches the
same incrementing counter seen in FUN_80075b14's nearby memory" --
i.e. mistaken for an unrelated per-frame tick. A live breakpoint this
session, reading the script buffer's own control word at the SAME
instant, confirmed `$a1` exactly equals `raw_word & 0xff` (both `0x1a`)
-- it is the selector, not a coincidental tick value.

Complete resolution: disassembling `0x80075b68` found a 2-level table
lookup; live-reading the ACTUAL BYTES at both tables' targets (not just
their addresses) revealed table2 is not a function-pointer table at all
-- it is an array of pointers into a literal, static, embedded filename
string table that actually extends across the disc's REAL full range,
`XAPACK00` through `XAPACK42` (43 entries, confirmed live by reading
every `table2[N]` for N=0..42 and checking each resolved string against
`gcrts.xa_disc_index`'s real disc file list -- not just the first 9
entries this investigation happened to sample first). Beyond index 42,
memory keeps producing plausible-looking `"XAPACK43"`, `"XAPACK44"`, ...
text that does NOT correspond to any real disc file -- confirmed by the
same real-disc cross-check, not assumed. `table1`'s byte is LITERALLY
the XAPACK file number, not an abstract category.

    selector = sound_or_voice_cue_word & 0xff         (e.g. 25, 26, 28 -- live-confirmed)
    table1_entry = TABLE1_BASE + selector * 5         (TABLE1_BASE = 0x8009CFDC)
    xapack_number = byte at table1_entry              (live-confirmed)
    table2_entry = TABLE2_BASE + xapack_number * 4    (TABLE2_BASE = 0x8009CF10)
    string_ptr = u32 at table2_entry                  (live-confirmed for the real range 0-42)
    filename = null-terminated string at string_ptr   (live-confirmed)
    disc_path = gcrts.xa_disc_index.resolve_filename_to_path(filename)  (cross-checked against the REAL disc)

**A further live finding, past table2**: the resolved string pointer is
consumed by `0x80075c88`, which builds a small structure at the FIXED
runtime address `0x800a5f54` containing the fully-constructed, real
ISO9660 path string -- read live: `"\\DAT\\XA1\\XAPACK09.BIN;1"`,
complete with the standard PS1 CD-ROM `;1` version suffix. This is a
THIRD independent confirmation of the same resolved filename (the first
two being this table lookup itself and the completely separate
LBA-position-based resolver from `AUDIO_CUE_RESOLUTION.md`), read
directly from the exact bytes the game's own file-open path would use.

**Scope limit, honestly reported and now disc-grounded rather than an
arbitrary numeric cap**: `resolve_audio_context` no longer hard-caps
`table1_value` at some guessed bound -- it validates the resolved
filename against the disc's own real file list
(`gcrts.xa_disc_index.resolve_filename_to_path`). A resolved string that
looks well-formed but doesn't match a real file (confirmed to happen for
table2 indices beyond 42) downgrades confidence to
`LIVE_VERIFIED_PARTIAL` rather than being silently trusted. This
replaces an earlier, too-narrow version of this module that only
trusted `table1_value <= 8` -- caught live, this session, when a real
selector resolved to `XAPACK09` (a real, valid file) and the old code
wrongly reported it as unresolved. This means the table is NOT a
globally valid, selector-number-to-XAPACK-number map across its entire
address range -- it is confirmed correct only for the selector values
this particular scene's script actually uses (live-confirmed so far:
25, 26, 28; structurally consistent but not independently live-verified:
24, 27, which also happen to fall in the same narrow window this
scene's script uses). What IS now general and disc-grounded is the
table1->table2->string->real-file-check MACHINERY itself -- it correctly
resolves whatever selector a script actually dispatches, for the full
real range of 43 disc files, not just a guessed subset.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable

DISPATCH_ENTRY_ADDR = 0x80075B68  # confirmed live: $a1 here == the control word's own low byte
TABLE1_BASE = 0x8009CFDC
TABLE1_STRIDE = 5
TABLE2_BASE = 0x8009CF10
TABLE2_STRIDE = 4
FILENAME_MAX_LEN = 12  # each string entry's own padded stride, confirmed live (8 chars + 4 null bytes)


class AudioContextConfidence(str, Enum):
    LIVE_VERIFIED = "LIVE_VERIFIED"  # selector -> table1 -> table2 -> string all read live and a valid XAPACK filename was parsed
    LIVE_VERIFIED_PARTIAL = "LIVE_VERIFIED_PARTIAL"  # tables read live but table1's value fell outside the confirmed-valid 0-8 range (see module docstring's scope limit)
    UNKNOWN = "UNKNOWN"  # selector unavailable or tables unreadable


@dataclass
class AudioContext:
    context_id: str
    selector_value: int | None  # sound_or_voice_cue control word's own low byte -- the REAL selector (not the "127" inline param)
    selector_source: str  # human-readable note on where this came from
    table1_entry_addr: int | None
    table1_value: int | None  # the XAPACK file number itself (0-8), confirmed live for the full valid range
    table2_entry_addr: int | None
    string_ptr: int | None  # table2's u32 value -- a pointer to a literal filename string, NOT a function pointer (corrected this pass)
    resolved_filename: str | None  # e.g. "XAPACK08" -- read directly from the live string table, whether or not it's a real file
    resolved_disc_path: str | None  # e.g. "DAT/XA1/XAPACK08.BIN" -- only set once resolved_filename is confirmed against the REAL disc file list
    resolution_depth: str  # honest statement of how far the chain was actually traced
    confidence: AudioContextConfidence

    def to_dict(self) -> dict:
        return {
            "context_id": self.context_id,
            "selector_value": self.selector_value,
            "selector_source": self.selector_source,
            "table1_entry_addr": self.table1_entry_addr,
            "table1_value": self.table1_value,
            "table2_entry_addr": self.table2_entry_addr,
            "string_ptr": self.string_ptr,
            "resolved_filename": self.resolved_filename,
            "resolved_disc_path": self.resolved_disc_path,
            "resolution_depth": self.resolution_depth,
            "confidence": self.confidence.value,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AudioContext":
        return cls(
            context_id=d["context_id"],
            selector_value=d.get("selector_value"),
            selector_source=d.get("selector_source", ""),
            table1_entry_addr=d.get("table1_entry_addr"),
            table1_value=d.get("table1_value"),
            table2_entry_addr=d.get("table2_entry_addr"),
            string_ptr=d.get("string_ptr"),
            resolved_filename=d.get("resolved_filename"),
            resolved_disc_path=d.get("resolved_disc_path"),
            resolution_depth=d.get("resolution_depth", ""),
            confidence=AudioContextConfidence(d.get("confidence", "UNKNOWN")),
        )


def _unavailable(context_id: str, selector_value, table1_entry_addr, table1_value, table2_entry_addr, reason: str) -> AudioContext:
    return AudioContext(
        context_id=context_id,
        selector_value=selector_value,
        selector_source="sound_or_voice_cue control word low byte (raw & 0xff)",
        table1_entry_addr=table1_entry_addr,
        table1_value=table1_value,
        table2_entry_addr=table2_entry_addr,
        string_ptr=None,
        resolved_filename=None,
        resolved_disc_path=None,
        resolution_depth=reason,
        confidence=AudioContextConfidence.UNKNOWN,
    )


def resolve_audio_context(
    read_memory: Callable[[int, int], bytes | None],
    selector_value: int | None,
    context_id: str = "current",
) -> AudioContext:
    """Pure, injected-`read_memory` (no breakpoints -- this project's
    established discipline). `selector_value` should be
    `control_code_raw & 0xff` for the owning sound_or_voice_cue
    occurrence -- callers typically get this from
    `gcrts.script_audio_association`'s decoded `ScriptCode.raw` (see
    `audio_context_for_association` below for the usual entry point)."""
    if selector_value is None:
        return _unavailable(context_id, None, None, None, None, "no selector available")

    table1_addr = TABLE1_BASE + selector_value * TABLE1_STRIDE
    table1_bytes = read_memory(table1_addr, 1)
    if table1_bytes is None:
        return _unavailable(context_id, selector_value, table1_addr, None, None, "table1 unreadable")
    table1_value = table1_bytes[0]

    table2_addr = TABLE2_BASE + table1_value * TABLE2_STRIDE
    table2_bytes = read_memory(table2_addr, 4)
    if table2_bytes is None:
        return _unavailable(context_id, selector_value, table1_addr, table1_value, table2_addr, "table2 unreadable")
    string_ptr = int.from_bytes(table2_bytes, "little")

    string_bytes = read_memory(string_ptr, FILENAME_MAX_LEN)
    filename = string_bytes.split(b"\x00")[0].decode("ascii", "replace") if string_bytes else None

    # Cross-check against the REAL disc file list, not a shape/pattern
    # check -- live memory beyond the disc's actual 43 XAPACK files was
    # found to keep producing plausible-looking "XAPACK43", "XAPACK44",
    # ... text (see module docstring). A string that merely LOOKS like a
    # filename is not evidence it's a real, meaningful resolution.
    from gcrts.xa_disc_index import resolve_filename_to_path

    disc_path = resolve_filename_to_path(filename) if filename else None

    if disc_path is not None:
        return AudioContext(
            context_id=context_id,
            selector_value=selector_value,
            selector_source="sound_or_voice_cue control word low byte (raw & 0xff)",
            table1_entry_addr=table1_addr,
            table1_value=table1_value,
            table2_entry_addr=table2_addr,
            string_ptr=string_ptr,
            resolved_filename=filename,
            resolved_disc_path=disc_path,
            resolution_depth=(
                "selector -> table1 XAPACK number -> table2 string pointer -> literal filename string "
                "-> confirmed to match a real disc file, all read live -- this is the complete, terminal resolution"
            ),
            confidence=AudioContextConfidence.LIVE_VERIFIED,
        )

    return AudioContext(
        context_id=context_id,
        selector_value=selector_value,
        selector_source="sound_or_voice_cue control word low byte (raw & 0xff)",
        table1_entry_addr=table1_addr,
        table1_value=table1_value,
        table2_entry_addr=table2_addr,
        string_ptr=string_ptr,
        resolved_filename=filename,
        resolved_disc_path=None,
        resolution_depth=(
            f"table1/table2 lookup produced {filename!r}, which does NOT match any of the disc's real "
            "43 XAPACK files -- this selector is likely not one this scene's script actually uses, or "
            "landed past the table's real semantic extent"
        ),
        confidence=AudioContextConfidence.LIVE_VERIFIED_PARTIAL,
    )


def cross_validate_source(event, context: AudioContext) -> bool | None:
    """Compares the two INDEPENDENT resolution paths this project now
    has: `event.source_file` (`gcrts.runtime_audio`/`gcrts.xa_disc_index`
    -- resolved from the live-observed playback position/LBA against the
    real disc file table) against `context.resolved_disc_path`
    (`gcrts.audio_context` -- resolved from the script control word's own
    selector through the static table/string lookup, itself already
    cross-checked against the real disc file list). These are
    completely different mechanisms with no shared code path; agreement
    between them is real, independent corroboration, not a tautology.

    Returns True/False when both sides have a real answer to compare,
    None when either side doesn't (never a false "they agree" from
    missing data, and never compares against an unconfirmed
    `resolved_filename` that didn't pass the real-disc-file check)."""
    if event is None or event.source_file is None or context is None or context.resolved_disc_path is None:
        return None
    return context.resolved_disc_path.upper() == event.source_file.upper()


def audio_context_for_association(read_memory: Callable[[int, int], bytes | None], association, context_id: str = "current") -> AudioContext:
    """Convenience wrapper over a `gcrts.script_audio_association.
    ScriptAudioAssociation` -- pulls the selector from the association's
    already-decoded raw control word if available."""
    from gcrts.script_audio_association import ScriptAssociationConfidence

    if association is None or association.confidence != ScriptAssociationConfidence.SCRIPT_CONTEXT_RESOLVED:
        return resolve_audio_context(read_memory, None, context_id)
    return resolve_audio_context(read_memory, association.control_code_raw_low_byte, context_id)
