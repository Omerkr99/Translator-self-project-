"""XA Channel / Filter Runtime Resolution milestone: the real, live-
captured Setfilter call that selects this game's actual CD-ROM audio
channel -- the final gap `XA_STREAM_RESOLUTION.md` and
`gcrts.cdrom_driver_map` left open (the hardware register map and the
command protocol were confirmed there, but no live Setfilter value had
been caught).

## How this was found

Three earlier live-capture attempts caught nothing but Sync (`0x00`),
always from one fixed caller (`ra=0x80081bd4`) -- across roughly 200
real seconds of active gameplay, including two full voiced segments
actually playing. This looked like `0x80081C00` (the address this
project had assumed was "the" shared command-issue routine, based on
one earlier decoded call site) simply never carries Setfilter.

**A static scan fixed the real bug.** Rather than trusting the
originally-assumed stack offset for the command byte (`sp+0x11`, which
turned out to be a leftover/unrelated byte from an earlier line of the
same function), a scan of the full ~576KB loaded-code range for every
place that (a) loads the CD-ROM command-register pointer
(`0x800A30C0`'s target, confirmed live == `0x1F801801` exactly) into a
register, then (b) `sb`s a value into it, found exactly 3 real call
sites -- and at every one, the command byte is already sitting in `$v0`
at the trapping instruction, no stack-offset guessing required:

  - `0x8008182C` (`ra=0x80081788`)
  - `0x80081AC8`
  - `0x80081C2C` (a few instructions past the OLD, wrongly-assumed
    `0x80081C00` entry point -- this is the address the original
    capture should have used)

**Software breakpoints at all 3, reading `$v0` directly, immediately
found real, varied command traffic** (a wide histogram of command
bytes, unlike the flat all-Sync result from the old single address) --
and, within seconds of a fresh dispatch, a genuine Setfilter (`0x0D`)
hit at `0x8008182C`. **Reproduced byte-identical on a second,
independent capture** (same call site, same register values, same
dereferenced parameter buffer) -- not a one-off/noise result.

## The real values

At the `0x8008182C` hit: `$a0=2` (parameter count -- matches
Setfilter's own real, publicly-documented 2-parameter protocol
exactly), `$a1=0x800A3070` (pointer to the parameter buffer, live-
dereferenced at the exact hit instant, before resuming), buffer
contents `[2, 1, 0, 0, ...]` (each parameter stored as a 4-byte-aligned
word; only the low byte is meaningful once narrowed for the actual
1-byte hardware write). Under the standard documented Setfilter
parameter order (file number, channel number): **file=2, channel=1**.

`file=2` is cross-validated here against the real disc catalog
(`gcrts.xa_disc_index.resolve_filename_to_path("XAPACK02")` resolves to
a real disc file, `DAT/XA1/XAPACK02.BIN`) -- not a guess. There was no
simultaneous LBA/position-counter read at the exact hit instant in this
session's capture (the capture script didn't request one), so this is
NOT triple-cross-validated the way `AUDIO_CONTEXT_RESOLUTION.md`'s
selector-table chain is; the semantic file/channel labeling rests on
the standard documented parameter order, not an independent same-instant
position check. Reported honestly as `LIVE_CAPTURED` for the raw
register/memory evidence.

## Important follow-up correction: NOT proven to be per-event

A later milestone (Audio Event Isolation / Extraction, see
`AUDIO_EVENT_EXTRACTION.md`) re-captured this exact same Setfilter call
site, this time also reading the live position counter, playback state,
and `last_req_params` at the EXACT SAME instant as the hit -- twice
independently (fresh state reload each time), always with
byte-identical results:

  - `params` always exactly `[2, 1]`, never varying
  - `state` always `0x02` (STOPPED), never caught during STARTING/PLAYING
  - `last_req_params` always a stale, already-finished cue's value,
    never a fresh dispatch's parameters
  - `position_counter` varying wildly between captures (observed once
    at 182935, deep in `XAPACK42`'s range -- nowhere near `XAPACK02`)

This is real, reproduced evidence that this specific Setfilter call is
**most likely a fixed default/reset value issued during idle periods,
not a per-event channel selection**. `KNOWN_SETFILTER_OBSERVATIONS`
below is kept exactly as originally captured (real, reproduced, honest
evidence of the mechanism and protocol), but callers must NOT treat it
as "the channel for whatever `RuntimeAudioEvent` happens to be active."
`gcrts.audio_event_extraction` enforces this directly: it never
defaults `xa_file_number`/`xa_channel` to this observation's values --
a caller must supply values independently confirmed for the specific
event being extracted.

## Second follow-up: the "one cue -> one Setfilter" model is wrong; this looks like a PERSISTENT filter instead

A later milestone (Per-Event XA Channel Capture) armed the same
lifecycle + command monitoring on the CURRENT live game state (not a
static save reload) for ~460 real seconds while the user actually
played through and confirmed hearing real audio. Two things came out
of this, both important:

1. **`params=(2, 1)` never varied across 8 separate Setfilter hits**,
   even though the position counter visited 5 different values in that
   same window (`158842`, `181469`, `178857`, `0`, `161793`) -- the
   disc-seek target clearly changed while the filter parameters did
   not. `filter_appears_persistent()` records this: not proof the
   filter can never change, but real, positive evidence that ONE
   filter setting stays valid across many housekeeping cycles and (per
   the confirmed real audio) at least one genuine playback. This is the
   more useful reframing the milestone itself suggested: not "which cue
   selects this filter" (a question three separate live-capture designs
   have now failed to answer) but "how long does one filter setting
   last" -- a question this evidence actually supports.
2. **The audio lifecycle state byte (`0x800A6107`) never once left
   `STOPPED` (`0x02`) across the entire ~460-second window**, despite
   confirmed real audio playing during it. See
   `gcrts.runtime_audio`'s own module docstring for the corresponding
   honest caveat this added to the STARTING/PLAYING/STOPPED lifecycle
   model -- that byte's earlier-confirmed transitions are real, but
   this session shows it does not reliably transition for every real,
   audible playback event.

## Why this isn't a live-pollable function

Every other resolver in this package (`runtime_audio.capture_audio_event`,
`audio_context.resolve_audio_context`, etc.) works by polling a fixed set
of RAM addresses -- no breakpoints, deliberately, per this project's own
standing discipline (breakpoint/continue overhead has caused real hangs
and timing distortion earlier in this project's history). Setfilter is
a one-shot event with no persistent, pollable field holding "the last
Setfilter's real parameters" anywhere in RAM that this investigation
found -- catching it required an actual live GDB breakpoint session
(arm at the 3 call sites, continue, inspect `$v0`/`$a1` on each hit).
This module therefore does NOT provide a `capture_setfilter_live(read_memory)`
function the way the rest of the package does. It documents the
confirmed, reproducible facts from this session's real breakpoint
captures instead -- the same pattern `gcrts.runtime_audio.KNOWN_CUE_SOURCES`
already established for a real, one-time, timestamped observation with
no general live-polling path.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# The confirmed, real hardware command-register write site for Setfilter
# specifically -- one of 3 real command-issuing call sites found by the
# static scan described above. At this exact address, $v0 already holds
# the command byte about to be written to the real hardware command
# register (0x1F801801, confirmed in gcrts.cdrom_driver_map).
SETFILTER_CALL_SITE_ADDR = 0x8008182C

# The other 2 real command-write call sites the same scan found --
# confirmed live-active (both fired constantly with real command
# traffic this session) but never observed carrying Setfilter.
OTHER_COMMAND_WRITE_SITES = (0x80081AC8, 0x80081C2C)

# The shared "next command to send" staging byte -- code at
# SETFILTER_CALL_SITE_ADDR loads $v0 from here (as a single byte)
# immediately before writing it to hardware.
COMMAND_STAGING_BYTE_ADDR = 0x800A30D4

# Per psx-spx / LibPSn00b Runtime Library Reference: "Setfilter -- Sets
# XA audio filter," 2 parameters (file number, channel number). Public
# documentation, not derived from this session's own guesswork.
SETFILTER_COMMAND = 0x0D


class SetfilterEvidenceConfidence(str, Enum):
    LIVE_CAPTURED = "LIVE_CAPTURED"  # a real, live GDB breakpoint hit, reproduced identically across 2+ independent captures this session
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class SetfilterCallObservation:
    """One real, live-captured Setfilter call -- register state and the
    dereferenced parameter buffer, read at the exact instant of the
    hardware write (before resuming execution).

    `file_number`/`channel_number` are `params[0]`/`params[1]` under the
    interpretation that `param_count` (== 2, matching Setfilter's own
    real protocol exactly) counts entries in the `params_ptr`-pointed
    buffer in the standard, publicly-documented (file, channel) order --
    not proven by an independent, simultaneous LBA/position-counter
    cross-check (see module docstring)."""

    call_site_addr: int
    ra: int
    param_count: int
    params_ptr: int
    params: tuple[int, ...]
    confidence: SetfilterEvidenceConfidence

    @property
    def file_number(self) -> int | None:
        return self.params[0] if len(self.params) > 0 else None

    @property
    def channel_number(self) -> int | None:
        return self.params[1] if len(self.params) > 1 else None

    def to_dict(self) -> dict:
        return {
            "call_site_addr": self.call_site_addr,
            "ra": self.ra,
            "param_count": self.param_count,
            "params_ptr": self.params_ptr,
            "params": list(self.params),
            "file_number": self.file_number,
            "channel_number": self.channel_number,
            "confidence": self.confidence.value,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SetfilterCallObservation":
        return cls(
            call_site_addr=d["call_site_addr"],
            ra=d["ra"],
            param_count=d["param_count"],
            params_ptr=d["params_ptr"],
            params=tuple(d["params"]),
            confidence=SetfilterEvidenceConfidence(d.get("confidence", "UNKNOWN")),
        )


# Two independent, real, live GDB breakpoint captures this session, both
# at SETFILTER_CALL_SITE_ADDR, byte-identical -- see
# XA_STREAM_RESOLUTION.md for the full transcript. Kept as documented
# historical evidence, the same pattern
# gcrts.runtime_audio.KNOWN_CUE_SOURCES already established: a real,
# timestamped observation, not a claim that file=2/channel=1 holds for
# every cue (this whole project's own investigation already proved a
# raw script parameter/selector alone does not stably identify one
# physical source -- see runtime_audio's own module docstring).
KNOWN_SETFILTER_OBSERVATIONS: tuple[SetfilterCallObservation, ...] = (
    SetfilterCallObservation(
        call_site_addr=SETFILTER_CALL_SITE_ADDR,
        ra=0x80081788,
        param_count=2,
        params_ptr=0x800A3070,
        params=(2, 1),
        confidence=SetfilterEvidenceConfidence.LIVE_CAPTURED,
    ),
)


@dataclass(frozen=True)
class SetfilterContextCheck:
    """One live capture that read the position counter, playback state,
    and last-requested params at the EXACT SAME instant as a Setfilter
    hit -- the cross-check that revealed the observation above is not
    proven event-specific (see module docstring)."""

    t_seconds_after_resume: float
    params: tuple[int, ...]
    position_counter_at_hit: int
    state_at_hit: int
    last_req_params_at_hit: int

    def to_dict(self) -> dict:
        return {
            "t_seconds_after_resume": self.t_seconds_after_resume,
            "params": list(self.params),
            "position_counter_at_hit": self.position_counter_at_hit,
            "state_at_hit": self.state_at_hit,
            "last_req_params_at_hit": self.last_req_params_at_hit,
        }


# Two independent live captures (Audio Event Isolation / Extraction
# milestone, fresh state reload before each), each reading
# position/state/last_req_params at the exact same instant as the
# Setfilter hit -- see AUDIO_EVENT_EXTRACTION.md. Both:
# params=(2, 1) unchanged, state=STOPPED (0x02), and a stale
# last_req_params -- the evidence behind `is_proven_event_specific()`.
# The identical position_counter value across both (182935) is itself
# informative: consistent with a fully deterministic replay from the
# same frozen save state, not a value influenced by live gameplay.
KNOWN_SETFILTER_CONTEXT_CHECKS: tuple[SetfilterContextCheck, ...] = (
    SetfilterContextCheck(
        t_seconds_after_resume=5.188129663467407,
        params=(2, 1),
        position_counter_at_hit=182935,
        state_at_hit=0x02,
        last_req_params_at_hit=0x0000007F,
    ),
    SetfilterContextCheck(
        t_seconds_after_resume=5.26,
        params=(2, 1),
        position_counter_at_hit=182935,
        state_at_hit=0x02,
        last_req_params_at_hit=0x0000007F,
    ),
    # Per-Event XA Channel Capture milestone: armed lifecycle + command
    # monitoring on the CURRENT live game state (not a static reload)
    # for ~460 real seconds while the user actually played through and
    # confirmed hearing real audio. Every one of 8 Setfilter hits in
    # this window: params=(2, 1), state=STOPPED (0x02) -- despite the
    # position counter visiting five DIFFERENT values across the window
    # (158842, 181469, 178857, 0, 161793), including one that isn't a
    # valid XA position at all (0). Setfilter never varied even though
    # the disc-seek target clearly did -- decisive evidence this call's
    # parameters are NOT selected per playback target. See
    # CDROM_SETFILTER_CAPTURE.md for the full transcript and the
    # "filter lifetime, not filter selection" reframing this motivated.
    SetfilterContextCheck(t_seconds_after_resume=275.84, params=(2, 1), position_counter_at_hit=158842, state_at_hit=0x02, last_req_params_at_hit=0x0000007F),
    SetfilterContextCheck(t_seconds_after_resume=279.14, params=(2, 1), position_counter_at_hit=181469, state_at_hit=0x02, last_req_params_at_hit=0x0000007F),
    SetfilterContextCheck(t_seconds_after_resume=394.72, params=(2, 1), position_counter_at_hit=0, state_at_hit=0x02, last_req_params_at_hit=0x0000007F),
    SetfilterContextCheck(t_seconds_after_resume=403.65, params=(2, 1), position_counter_at_hit=158842, state_at_hit=0x02, last_req_params_at_hit=0x0000007F),
    SetfilterContextCheck(t_seconds_after_resume=420.83, params=(2, 1), position_counter_at_hit=181469, state_at_hit=0x02, last_req_params_at_hit=0x0000007F),
    SetfilterContextCheck(t_seconds_after_resume=457.80, params=(2, 1), position_counter_at_hit=0, state_at_hit=0x02, last_req_params_at_hit=0x0000007F),
)


def is_proven_event_specific() -> bool:
    """False, honestly, per `KNOWN_SETFILTER_CONTEXT_CHECKS`: every
    simultaneous cross-check found the Setfilter call firing during a
    STOPPED state with a stale, already-finished cue's params -- never
    during STARTING/PLAYING with fresh params. Callers (e.g.
    `gcrts.audio_event_extraction`) must never treat
    `KNOWN_SETFILTER_OBSERVATIONS` as "the channel for the current
    event" based on this evidence alone."""
    return False


def filter_appears_persistent() -> bool:
    """True: across all 8 real-session observations
    (`KNOWN_SETFILTER_CONTEXT_CHECKS`), `params=(2, 1)` never changed
    even as the position counter visited 5 different values -- the
    disc-seek target clearly changed while the filter did not. This is
    the milestone's own suggested reframing: not "which cue selects
    this filter" (a question this project's evidence keeps failing to
    answer) but "how long does one filter setting stay valid" (a
    question this same evidence directly supports: at least across an
    entire ~460-second real play session including confirmed audible
    playback). Not proof the filter NEVER changes -- only that it did
    not change within this one observed window."""
    return True


def cross_validate_file_number(file_number: int) -> str | None:
    """Checks a Setfilter file-number parameter against the real disc
    catalog (gcrts.xa_disc_index) -- never trusts a plausible-looking
    small integer without this, the same discipline gcrts.audio_context
    and gcrts.audio_stream_source already apply to their own resolved
    values. Returns the real disc path if file_number names a real
    XAPACK file, else None."""
    from gcrts.xa_disc_index import resolve_filename_to_path

    return resolve_filename_to_path(f"XAPACK{file_number:02d}")
