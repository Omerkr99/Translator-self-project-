"""Runtime Audio Tracker: turns the Stage C `sound_or_voice_cue` call-chain
trace (BACKLOG_INVESTIGATION_RESULTS.md) into a reusable, live-pollable
capability, following the same pattern as `gcrts.renderer1_profile` /
`gcrts.renderer1_runtime` -- a profile of live addresses with a code
fingerprint that must validate before any read is trusted, and pure,
injected-`read_memory` functions so the actual decision logic is testable
without a live emulator.

What is LIVE-CONFIRMED this session (see RUNTIME_AUDIO_TRACKER.md for the
full evidence, including raw poll transcripts):

  - Of the "state pair" already known from Stage C, `0x800A6106` itself
    (the byte the pre-existing getter `0x80076118` actually reads) stayed
    `0x00` across every observation this session -- it is `0x800A6107`,
    the second byte, that carries real lifecycle information. (An early
    version of this module mis-read the two bytes as one little-endian
    `u16` -- `0x0001`/`0x0002` -- which matches neither byte's real value;
    caught by testing against live memory before trusting the model, not
    by inspection.) `0x800A6107` takes exactly three distinct values
    across a real lifecycle, observed in order: `0x00` (transient, seen
    only at the instant a save state carrying a fresh dispatch loads),
    `0x01` (sustained for 37+ real seconds while the position counter
    below was actively advancing -- PLAYING), `0x02` (sustained for 57+
    real seconds with the position counter frozen and `0x800A6114`
    cleared to zero -- STOPPED). This is the first live evidence of what
    this byte actually means; prior passes only observed it being
    written, never correlated it with playback activity over time.
  - `0x800A6114` (already confirmed as "last-requested raw parameters" by
    Stage C) reliably reads back to `0x00000000` once playback has fully
    stopped -- a second, independent signal agreeing with the state-pair
    transition above.
  - `0x800A61AC` (already known as the address `0x80080d54`'s MSF-to-LBA
    result is stored into, per Stage C's `0x80077928` decode) is NOT a
    one-shot value -- polled once every ~0.6-0.8s across two real sessions,
    it increased on almost every poll while state was `0x0001`, including
    real multi-second plateaus (plausibly natural speech pauses), and was
    completely frozen at a fixed value for 57+ consecutive seconds once
    state became `0x0002`. This is genuine, live-verified evidence it
    tracks playback progress in some form.

What is explicitly NOT confirmed, and must not be overclaimed:

  - The exact real-time UNIT of `0x800A61AC`'s value in the sense of
    "milliseconds elapsed" -- its observed rate of increase (~100-300 per
    second across three separate live sessions) does not cleanly match the
    fixed 75-raw-sectors/sec physical CD rate. `playback_offset_ms` is
    therefore derived from wall-clock polling time while state stays
    PLAYING, not from this counter's own scale.
  - Whether `0x800A61AC`'s value is scoped to "the current cue" at all.
    See the Audio Cue Resolution Generalization milestone below -- it is
    NOT reset to a small value at the start of each new cue; it behaves
    like a persistent, continuously-advancing position that a fresh
    breakpoint capture can land on almost anywhere depending on real
    elapsed time since the state was loaded.
  - `source_file` resolution for an arbitrary cue purely from its raw
    script parameter. See below -- this was actively disproven this
    session, not just unconfirmed.
  - That `0x800A6107` reliably transitions to `0x01` (PLAYING) for
    EVERY real, audible playback event. A much later milestone (Per-Event
    XA Channel Capture, see `gcrts.cdrom_setfilter`'s own module
    docstring and `CDROM_SETFILTER_CAPTURE.md`) polled this byte
    continuously for ~460 real seconds on the live, currently-running
    game state -- spanning a stretch the user directly confirmed
    included real, audible playback -- and it never once left `0x02`
    (STOPPED). This does not invalidate the earlier-confirmed
    transitions above (those were real, directly observed in a
    different session); it means this byte's transition to PLAYING is
    NOT a reliable signal for every real audio event, for reasons this
    project has not yet identified (possibilities include: the
    transition is much shorter-lived than this polling cadence can
    catch, or this specific byte tracks a narrower/different condition
    than "audio is currently audible"). Reported honestly rather than
    silently reconciled with the earlier finding.

## Audio Cue Resolution Generalization milestone (follow-up session)

Set out to build a general `script_parameter -> physical source` table
by tracing more cues the way Stage C traced 127. What was actually found
is more interesting, and changes this module's whole resolution
strategy:

**The raw script parameter alone does NOT stably identify one physical
source.** Two independent live breakpoint captures of `0x80080d54`
(same save state, same confirmed dispatch site `ra=0x80077968`, both
with `last_req_params` reading `127` at the moment of the call) computed
LBAs in two DIFFERENT `XAPACK*.BIN` files depending on how much real
wall-clock time had passed since the state loaded -- one landed at LBA
`116010` (`DAT/XA1/XAPACK06.BIN`'s own start LBA, exactly), the other at
LBA `127781`-`128464` (`DAT/XA1/XAPACK08.BIN`, matching Stage C's
original capture). A 40-hit continuous capture of the confirmed dispatch
site showed WHY: it fires repeatedly (roughly 6x/second) while a cue is
active, each call computing a SLIGHTLY LARGER LBA than the last (a smooth
~100-104/sec climb) -- not a one-shot "here is cue 127's target," but a
persistent, continuously-advancing value. `0x800A61AC` (the address this
result is stored into) being fast-changing was already known from the
prior milestone; this session found the actual mechanism producing that
motion.

**A second, unrelated call site for the same shared `0x80080d54`
function was also found** (`ra=0x80077458`, inside a distinct function
around `0x80077400` that takes an explicit minutes/seconds/frames-shaped
argument set and combines a base LBA with a computed time offset --
architecturally closer to a general "seek to time T" primitive than the
simple cue dispatcher). Confirms `0x80080d54` is genuinely shared,
low-level infrastructure used by at least two different subsystems, not
sound-cue-specific.

**A third finding directly disproves treating a recomputed LBA's own
`channel_number` byte as "the active playback channel"**: across 40
consecutive real calls, `channel_number` was found to be an EXACT,
purely positional function of `(lba - file_start_lba) % 8` -- the
standard 8-way CD-XA interleave pattern, confirmed to the byte. This is
mechanically expected of ANY position within an interleaved file; it is
NOT independent evidence of which channel the SPU is actually decoding.
Stage C's original "channel 7" finding for cue 127 is consistent with
this (`(126921-126218) % 8 == 7`, exactly) but should be read as "the
channel of the specific sector the game happened to compute a target
at," not as a confirmed, general channel-selection fact.

**What this means for resolution, going forward**: `source_file` is now
resolved LIVE from whatever LBA is actually observed
(`gcrts.xa_disc_index.resolve_lba_to_file`, a static, exact table built
from the real disc's own ISO9660 directory records) -- general and
always correct for ANY position genuinely observed, unlike a per-cue
table. `KNOWN_CUE_SOURCES` is kept only as a historical fallback/
regression fixture (one specific, timestamped observation), used ONLY
when live LBA resolution is unavailable, never treated as authoritative
over a live reading. `xa_channel` is still computed (from
`gcrts.xa_disc_index.read_sector_meta`, when disc bytes are available)
but reported with an honestly lower-confidence label given the
positional-artifact finding above -- see `AudioConfidence.
POSITIONAL_UNCONFIRMED`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from gcrts.xa_disc_index import read_sector_meta, resolve_lba_to_file

STATE_PAIR_ADDR = 0x800A6106
LAST_REQ_PARAMS_ADDR = 0x800A6114
POSITION_ADDR = 0x800A61AC
FLAGS_ADDR = 0x800A61B8

# Fingerprint: the first 24 bytes of 0x800760b4, the confirmed
# "raw_index -> last_req_params store, then hand off to 0x80077808" trigger
# function (Stage C follow-up #3) -- CODE, never written by this tracker,
# so validation can never be invalidated by this module's own activity.
# Captured live this session while save-state slot 3's dispatch was active.
FINGERPRINT_ADDR = 0x800760B4
FINGERPRINT_BYTES = bytes.fromhex("e0ffbd27211080002118a0002140c0000a80013c176127a0")


class AudioLifecycleState(str, Enum):
    """CAVEAT (Real Audio Playback Truth milestone -- see module
    docstring's newest section and gcrts.audio_playback_truth): PLAYING
    and STOPPED here describe the raw 0x800A6107 byte's own values,
    live-confirmed to correlate with SOME real playback session in an
    earlier, separate observation -- they are NOT confirmed to mean
    "audio is audibly playing right now" in general. A later ~460-second
    session with confirmed real, audible playback throughout never once
    saw this byte leave STOPPED. Treat PLAYING/STOPPED as the engine
    byte's own raw state, not as audible-playback ground truth, until a
    real replacement signal is found."""

    REQUESTED = "REQUESTED"  # command byte written, not yet observed live as its own distinct raw value
    STARTING = "STARTING"  # raw state 0x0000 -- observed only transiently, at the instant of a fresh dispatch
    PLAYING = "PLAYING"  # raw state 0x0001 -- LIVE-CONFIRMED to correlate with SOME real playback session; NOT confirmed general (see class docstring)
    PAUSED = "PAUSED"  # not observed live this session -- reserved for future evidence
    STOPPED = "STOPPED"  # raw state 0x0002 -- LIVE-CONFIRMED to correlate with SOME real playback session; NOT confirmed general -- also observed throughout a real, audible ~460s session (see class docstring)
    UNKNOWN = "UNKNOWN"  # raw state byte seen that doesn't match any confirmed value


class AudioConfidence(str, Enum):
    LIVE_EXACT = "LIVE_EXACT"  # this exact field was live-captured and cross-checked this session
    LIVE_LBA_RESOLVED = "LIVE_LBA_RESOLVED"  # source_file resolved from a live-observed LBA against the real, exact disc file table -- general, not a guess, but says nothing about WHICH channel
    POSITIONAL_UNCONFIRMED = "POSITIONAL_UNCONFIRMED"  # a value exists (e.g. xa_channel) but is only known to be a positional artifact of the disc's interleaving, not independently confirmed as the true playback selection
    LIVE_INFERRED = "LIVE_INFERRED"  # derived from live data but not independently cross-checked
    STATIC_LOOKUP = "STATIC_LOOKUP"  # from KNOWN_CUE_SOURCES -- a historical, one-time observation, not re-derived live this call, and not guaranteed to still hold (see module docstring: the same param has been observed pointing to two different files)
    UNKNOWN = "UNKNOWN"


_RAW_STATE_TO_LIFECYCLE = {
    0x0000: AudioLifecycleState.STARTING,
    0x0001: AudioLifecycleState.PLAYING,
    0x0002: AudioLifecycleState.STOPPED,
}

# HISTORICAL FALLBACK ONLY -- see module docstring's "Audio Cue Resolution
# Generalization" section. Stage C's one-time capture of script parameter
# 127 (BACKLOG_INVESTIGATION_RESULTS.md, "Stage C live follow-up #5"):
# LBA 126921 -> DAT/XA1/XAPACK08.BIN -> channel 7, mono 4-bit XA-ADPCM.
# A LATER live capture of the SAME parameter (127) resolved to a
# DIFFERENT file (XAPACK06.BIN) -- this table is not proven to generalize
# even to repeat observations of the same value, let alone new ones.
# `capture_audio_event` only falls back to this when live LBA resolution
# isn't available (e.g. position_counter reads outside any known XAPACK
# file's range); a live reading always takes priority.
KNOWN_CUE_SOURCES: dict[int, dict] = {
    127: {
        "source_file": "DAT/XA1/XAPACK08.BIN",
        "xa_channel": 7,
        "start_lba": 126921,
        "audio_category": 2,  # 0x80077928's own dispatch value, cross-confirmed against 0x80075d34's a2
    }
}


@dataclass
class AudioProfile:
    """Everything the tracker needs to read one loaded state's sound-cue
    system, plus how much live evidence backs it -- mirrors
    gcrts.renderer1_profile.Renderer1Profile exactly, same reasoning:
    addresses captured against one loaded executable/state are not
    automatically portable to another."""

    profile_name: str
    state_pair_addr: int = STATE_PAIR_ADDR
    last_req_params_addr: int = LAST_REQ_PARAMS_ADDR
    position_addr: int = POSITION_ADDR
    flags_addr: int = FLAGS_ADDR
    fingerprint_addr: int = FINGERPRINT_ADDR
    fingerprint_bytes: bytes = FINGERPRINT_BYTES
    notes: str = ""


SLPS00102_AUDIO_PROFILE = AudioProfile(
    profile_name="SLPS00102_base_audio",
    notes=(
        "Live-confirmed this session against save-state slot 3 (the same "
        "dialogue scene Stage C's sound-cue chain was traced against). "
        "Fingerprint is 0x800760b4's own function-entry bytes -- code, "
        "never touched by this tracker's own reads."
    ),
)


def validate_profile(profile: AudioProfile, read_memory: Callable[[int, int], bytes | None]) -> bool:
    """Pure, testable validation -- same contract as
    gcrts.renderer1_profile.validate_profile: never trust a profile's
    addresses without a live fingerprint match first."""
    live = read_memory(profile.fingerprint_addr, len(profile.fingerprint_bytes))
    return live == profile.fingerprint_bytes


@dataclass
class RuntimeAudioEvent:
    event_id: str
    source_type: str  # "voice" | "music" | "sfx" | "ambient" | "unknown" -- only "voice" is live-confirmed
    script_parameter: int | None
    audio_category: int | None  # the 0x80077928 dispatch value (2 = confirmed for the one traced cue)
    source_file: str | None
    xa_channel: int | None  # see AudioConfidence.POSITIONAL_UNCONFIRMED: a real value, not proven to be the true playback selection
    start_lba: int | None  # the LBA source_file/xa_channel were resolved from (live position_counter_start, or KNOWN_CUE_SOURCES as fallback)
    resolution_method: str  # "live_lba" | "static_table" | "unresolved" -- HOW source_file/xa_channel were determined
    position_counter: int | None  # raw live value of 0x800A61AC -- see module docstring: unit not confirmed
    position_counter_start: int | None  # position_counter's value when this event was first observed
    playback_offset_ms: float | None  # wall-clock elapsed while state==PLAYING, NOT derived from position_counter
    state: AudioLifecycleState
    confidence: AudioConfidence

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "source_type": self.source_type,
            "script_parameter": self.script_parameter,
            "audio_category": self.audio_category,
            "source_file": self.source_file,
            "xa_channel": self.xa_channel,
            "start_lba": self.start_lba,
            "resolution_method": self.resolution_method,
            "position_counter": self.position_counter,
            "position_counter_start": self.position_counter_start,
            "playback_offset_ms": self.playback_offset_ms,
            "state": self.state.value,
            "confidence": self.confidence.value,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RuntimeAudioEvent":
        return cls(
            event_id=d["event_id"],
            source_type=d.get("source_type", "unknown"),
            script_parameter=d.get("script_parameter"),
            audio_category=d.get("audio_category"),
            source_file=d.get("source_file"),
            xa_channel=d.get("xa_channel"),
            start_lba=d.get("start_lba"),
            resolution_method=d.get("resolution_method", "unresolved"),
            position_counter=d.get("position_counter"),
            position_counter_start=d.get("position_counter_start"),
            playback_offset_ms=d.get("playback_offset_ms"),
            state=AudioLifecycleState(d.get("state", "UNKNOWN")),
            confidence=AudioConfidence(d.get("confidence", "UNKNOWN")),
        )


def _lifecycle_for_raw_state(raw_state: int, last_req_nonzero: bool) -> AudioLifecycleState:
    state = _RAW_STATE_TO_LIFECYCLE.get(raw_state, AudioLifecycleState.UNKNOWN)
    # A cleared last_req_params is the second, independent signal Stage C's
    # own live poll found agreeing with raw_state==0x0002 -- if state says
    # STOPPED but params are still nonzero, that combination was never
    # observed live; report UNKNOWN rather than silently trusting one signal.
    if state == AudioLifecycleState.STOPPED and last_req_nonzero:
        return AudioLifecycleState.UNKNOWN
    return state


def capture_audio_event(
    read_memory: Callable[[int, int], bytes | None],
    profile: AudioProfile = SLPS00102_AUDIO_PROFILE,
    event_id: str = "current",
    prior: "RuntimeAudioEvent | None" = None,
    disc_bytes: bytes | None = None,
) -> RuntimeAudioEvent | None:
    """One-shot snapshot read (no breakpoints -- same discipline as
    gcrts.renderer1_runtime.capture_snapshot and for the same reason: this
    project's own history of GDB breakpoint/continue hangs). Returns None
    if the profile doesn't validate (wrong overlay/state loaded) or if the
    raw state byte has never been requested at all (both bytes zero AND
    last_req_params all zero -- genuinely nothing has ever been dispatched
    in this loaded state, distinct from a confirmed STOPPED-after-playing).

    `prior`, if given, carries `position_counter_start` forward so a
    caller polling repeatedly can compute relative progress within one
    contiguous PLAYING span rather than treating every call as a new
    event -- callers are responsible for their own polling cadence and
    for deciding when a new `event_id` should start (e.g. when
    `script_parameter` changes).

    `disc_bytes`, if given (a caller's own already-loaded copy of the raw
    disc image -- this function never opens a file itself), enables
    `xa_channel` resolution via `gcrts.xa_disc_index.read_sector_meta`.
    Without it, `xa_channel` is only ever populated from the
    `KNOWN_CUE_SOURCES` historical fallback, never live-derived.

    Resolution priority (see module docstring's "Audio Cue Resolution
    Generalization" section for why): live LBA resolution against the
    real disc file table is tried FIRST, using `position_counter_start`
    (general, always correct for any position actually observed).
    `KNOWN_CUE_SOURCES` is only consulted when that fails."""
    if not validate_profile(profile, read_memory):
        return None

    state_bytes = read_memory(profile.state_pair_addr, 2)
    params_bytes = read_memory(profile.last_req_params_addr, 4)
    position_bytes = read_memory(profile.position_addr, 4)
    if state_bytes is None or params_bytes is None or position_bytes is None:
        return None

    # The lifecycle-carrying byte is the SECOND byte of the pair
    # (0x800A6107), confirmed live this session -- 0x800A6106 itself (what
    # the pre-existing getter 0x80076118 reads) stayed 0x00 throughout
    # every observation. See module docstring for the mis-read this
    # corrects (treating the pair as one little-endian u16 matched neither
    # byte's real value).
    raw_state = state_bytes[1]
    last_req_nonzero = any(params_bytes)
    if raw_state == 0 and not last_req_nonzero:
        return None

    script_parameter = params_bytes[0] if last_req_nonzero else (prior.script_parameter if prior else None)
    position_counter = int.from_bytes(position_bytes, "little")
    lifecycle = _lifecycle_for_raw_state(raw_state, last_req_nonzero)

    position_counter_start = position_counter
    if prior is not None and prior.script_parameter == script_parameter and prior.position_counter_start is not None:
        position_counter_start = prior.position_counter_start

    # Priority 1: live LBA resolution against the real, exact disc file
    # table -- general, and correct for whatever is ACTUALLY observed,
    # unlike a per-cue table (see module docstring: the same raw
    # script_parameter has been observed pointing at two different files).
    source_file = None
    xa_channel = None
    start_lba = None
    resolution_method = "unresolved"
    confidence = AudioConfidence.UNKNOWN

    location = resolve_lba_to_file(position_counter_start) if position_counter_start is not None else None
    if location is not None:
        source_file = location.disc_path
        start_lba = position_counter_start
        resolution_method = "live_lba"
        confidence = AudioConfidence.LIVE_LBA_RESOLVED
        if disc_bytes is not None:
            meta = read_sector_meta(disc_bytes, position_counter_start)
            if meta is not None:
                # A real value, but see AudioConfidence.POSITIONAL_UNCONFIRMED
                # and the module docstring: this is confirmed to be a pure
                # positional artifact of the disc's own 8-way interleave,
                # NOT independently proven to be the true SPU decode channel.
                xa_channel = meta.channel_number
                confidence = AudioConfidence.POSITIONAL_UNCONFIRMED
    else:
        # Priority 2: KNOWN_CUE_SOURCES fallback -- only reached when live
        # resolution didn't land inside any known XAPACK file's range.
        source = KNOWN_CUE_SOURCES.get(script_parameter, {}) if script_parameter is not None else {}
        if source:
            source_file = source.get("source_file")
            xa_channel = source.get("xa_channel")
            start_lba = source.get("start_lba")
            resolution_method = "static_table"
            confidence = AudioConfidence.STATIC_LOOKUP

    audio_category = KNOWN_CUE_SOURCES.get(script_parameter, {}).get("audio_category") if script_parameter is not None else None

    return RuntimeAudioEvent(
        event_id=event_id,
        source_type="voice" if source_file else "unknown",
        script_parameter=script_parameter,
        audio_category=audio_category,
        source_file=source_file,
        xa_channel=xa_channel,
        start_lba=start_lba,
        resolution_method=resolution_method,
        position_counter=position_counter,
        position_counter_start=position_counter_start,
        playback_offset_ms=None,  # only a polling driver with wall-clock timestamps can fill this in
        state=lifecycle,
        confidence=confidence if source_file else AudioConfidence.LIVE_INFERRED,
    )


@dataclass
class AudioPollSample:
    """One timestamped poll result, produced by a live driver loop (see
    RUNTIME_AUDIO_TRACKER.md's live-verification script) -- kept separate
    from RuntimeAudioEvent because playback_offset_ms is only meaningful
    across a SEQUENCE of samples, not from a single read."""

    t: float
    event: RuntimeAudioEvent | None


def compute_playback_offset_ms(samples: list[AudioPollSample]) -> float | None:
    """Sums wall-clock time across consecutive samples where state stayed
    PLAYING for the same script_parameter -- deliberately NOT derived from
    position_counter's own scale (see module docstring: that scale is not
    confirmed). A gap where state left PLAYING and returned resets the
    accumulation, since that is evidence of a new/different playback span,
    not continuation of the one being measured."""
    total = 0.0
    prev: AudioPollSample | None = None
    for sample in samples:
        is_playing = sample.event is not None and sample.event.state == AudioLifecycleState.PLAYING
        prev_playing = (
            prev is not None
            and prev.event is not None
            and prev.event.state == AudioLifecycleState.PLAYING
            and prev.event.script_parameter == (sample.event.script_parameter if sample.event else None)
        )
        if is_playing and prev_playing:
            total += (sample.t - prev.t) * 1000.0
        prev = sample
    return total if any(s.event is not None and s.event.state == AudioLifecycleState.PLAYING for s in samples) else None
