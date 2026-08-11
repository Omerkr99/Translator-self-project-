"""Real Audio Playback Truth milestone: investigates what actually
represents AUDIBLE XA playback, after a live session proved
`gcrts.runtime_audio`'s `0x800A6107` byte cannot be trusted as that
signal (see that module's own docstring for the corresponding caveat).

## What this milestone found

**Disproof, not yet a replacement.** This module exists to hold that
honestly: `0x800A6107` is demoted from "PLAYING/STOPPED truth" to
`raw_engine_state` (meaning genuinely `UNKNOWN`), but no confirmed
alternative "this is audibly playing right now" signal was found this
pass, despite two separate search strategies:

1. **Decoded the real Setmode value from the previously-captured
   command cycle**: `0x01`. Per public PS1 documentation (psx-spx),
   that is ONLY bit 0 (CDDA) set -- bit 6 (XA-ADPCM, "send XA-ADPCM
   sectors to SPU Audio Input") and bit 3 (XA-Filter, "process only
   sectors matching Setfilter") are both OFF. This means the entire
   repeating `Setloc/Setmode/ReadN/Pause/Setfilter` cycle this project
   has captured multiple times is **not configured for XA audio
   playback at all** -- it reads plain data, and the Setfilter(2, 1)
   calls embedded in it have no functional effect (XA-Filter is off).
   This explains why that cycle never correlated with anything: it was
   never the audio path to begin with.
2. **The documented XA-ADPCM playback command is `ReadS` (`0x1B`)**, not
   `ReadN` (`0x06`) -- per psx-spx: "To play XA-ADPCM ... issue a Read
   command (typically ReadS)." `0x1B` has never appeared in ANY capture
   this project has taken across every milestone.
3. **A widened static scan** (searching up to 60 instructions past each
   load of the command-register pointer, versus the original 12) found
   4 additional raw hits beyond the 3 already-confirmed real sites --
   but direct disassembly of each showed they were false positives from
   register reuse (the same numbered register reloaded with a
   DIFFERENT, closer pointer between the original load and the
   store) or already-known parameter/request writes belonging to the
   same 3 known command sites. **No new genuine command-issuing site,
   and no `ReadS`, was found.**

Given this, the milestone's own Definition of Done (distinguish "the
byte says 0x02" from "audio is audibly playing" using live-confirmed
evidence) was **not fully met** -- the disproof is confirmed and real;
the replacement signal remains an open search. This is reported
honestly rather than forcing a plausible-looking but unverified
`AudiblePlaybackState` definition into existence.

## The one genuinely new site found (not audio-related)

The static scan's real (non-false-positive) additions were parameter/
request-register writes belonging to `0x80081AC8`'s own already-known
function, which turned out to be a generic "send a 4-byte command
struct" helper (writes `struct[0]`->param, `struct[1]`->request,
`3`->index, `struct[2]`->command, `struct[3]`->param, `0x20`->request,
in that order) -- the same architectural pattern Stage C found for
`0x80077808` much earlier in this project. This explains why `0x7F`/
`0x80` (observed at this site, not real documented CD-ROM command
numbers) appeared: this helper is very likely reused by more than one
caller for more than one purpose, and `struct[2]` is only a genuine
"CD-ROM command byte" for SOME of those callers, not necessarily the
ones that produced `0x7F`/`0x80`. Not resolved further this pass --
reported as observed, not assigned an invented meaning.
"""
from __future__ import annotations

from enum import Enum


class AudiblePlaybackState(str, Enum):
    """Deliberately mostly unused. Only `UNKNOWN` has any live evidence
    behind it this session -- see module docstring. Kept as an enum
    (rather than a bare comment) so a FUTURE milestone that does find a
    real signal has a natural place to add e.g. `AUDIBLE_XA` without
    redesigning the shape of this module."""

    UNKNOWN = "UNKNOWN"


# Real value captured live and decoded against public PS1 documentation
# (psx-spx) -- NOT this project's own interpretation. Bit 6 (XA-ADPCM)
# and bit 3 (XA-Filter) are both clear; only bit 0 (CDDA) is set.
OBSERVED_SETMODE_VALUE = 0x01
SETMODE_XA_ADPCM_BIT = 0x40
SETMODE_XA_FILTER_BIT = 0x08
SETMODE_CDDA_BIT = 0x01

# Per psx-spx: the documented command for actually playing XA-ADPCM
# sectors. Never observed in any capture this project has taken.
READS_COMMAND = 0x1B


def observed_setmode_has_xa_audio_bits() -> bool:
    """False: the one real Setmode value this project has ever captured
    (0x01) does not have the XA-ADPCM or XA-Filter bits set. Real,
    decoded fact -- not a guess."""
    return bool(OBSERVED_SETMODE_VALUE & (SETMODE_XA_ADPCM_BIT | SETMODE_XA_FILTER_BIT))


def raw_engine_state_meaning() -> str:
    """Honest classification of `gcrts.runtime_audio`'s `0x800A6107`
    byte, per this milestone's live evidence: a ~460-second session
    with confirmed real, audible playback never once saw this byte
    leave STOPPED (0x02). Its real role is UNKNOWN -- not proven to be
    request state, command state, decoder state, or anything else
    specific; only proven NOT to reliably indicate audible playback."""
    return "UNKNOWN"
