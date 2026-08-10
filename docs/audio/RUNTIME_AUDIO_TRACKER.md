# Runtime Audio Tracker

Milestone goal: prove `START -> PLAYING -> current offset -> STOP` for a
real voice cue, live, and make that available through `RuntimeSnapshot` --
closing the "playback lifetime" gap `CURRENT_SYSTEM_STATUS.md` flagged as
open after Stage C's script-cue-to-disc-sector trace. New module:
`gcrts/runtime_audio.py`. Wired into `gcrts/runtime_visual_provider.py`
(`RuntimeVisualProvider._audio_event`, cached on
`provider.last_audio_event`, same pattern as `last_renderer1_validation`)
and `gcrts/runtime_snapshot.py` (`active_audio` is no longer an always-
empty placeholder). A minimal read-only panel was added to
`gcrts/visual_inspector_ui.py`. 25 new tests
(`tests/test_runtime_audio.py`, `tests/test_runtime_snapshot.py`'s new
audio section); full suite **425 passed** (400 + 25), no regressions.

**Follow-up milestone (Audio Cue Resolution Generalization,
`AUDIO_CUE_RESOLUTION.md`)**: the source-resolution half of this
document (originally: a small `KNOWN_CUE_SOURCES` table keyed by raw
script parameter) has been superseded by a more general, live mechanism
-- resolving `source_file` from whatever LBA is actually observed
(`gcrts.xa_disc_index.resolve_lba_to_file`, an exact table built from
the disc's own file records) rather than a per-cue lookup. This was a
necessary correction, not just an enhancement: the same raw script
parameter was live-observed resolving to two different physical files
at different times, disproving the original table's implicit assumption
that a script parameter is a stable source identifier. See
`AUDIO_CUE_RESOLUTION.md` for the full evidence and
`gcrts/runtime_audio.py`'s module docstring for the current, correct
summary. `KNOWN_CUE_SOURCES` is retained only as a documented,
last-resort fallback. Test count: **438 passed** (425 + 13: 10 in
`tests/test_xa_disc_index.py`, net +3 in `tests/test_runtime_audio.py`).

**Second follow-up milestone (Script Context <-> Audio Dispatch
Correlation, `SCRIPT_AUDIO_ASSOCIATION.md`)**: answers the question
`AUDIO_CUE_RESOLUTION.md` left open -- why the same raw parameter
resolves to different files. New module
`gcrts/script_audio_association.py` correlates the live script cursor
(`0x800A4CEA`, already confirmed by a prior session's
`DECODER_READ_CURSOR.md`) and decoded script buffer against each live
`RuntimeAudioEvent`, live-proving across 4 real samples that a
content-based fingerprint of the owning `ScriptUnit` -- not word offset,
not the raw parameter -- correlates exactly with which physical file
gets used. Wired into `RuntimeVisualProvider.last_script_association`
and `RuntimeSnapshot.active_audio`'s new nested `"script_context"`
field. Test count: **452 passed** (438 + 14).

**Third follow-up milestone (Audio Context Resolution +
Audio Captions, `AUDIO_CONTEXT_RESOLUTION.md` + `AUDIO_CAPTIONS.md`)**:
found the actual causal mechanism -- the "127" inline parameter every
prior pass tracked was never the real per-line selector; the
`sound_or_voice_cue` control WORD's own low byte is, live-confirmed and
traced through a real 2-level table dispatch (`gcrts/audio_context.py`).
Also added a semantic "what is being heard" layer
(`gcrts/audio_caption.py`) kept strictly separate from source/context
identity, honestly limited to real dialogue text as its only
self-produced caption source (no audio listening capability exists in
this environment -- no SFX/ambient descriptions are fabricated). Both
wired into `RuntimeVisualProvider`/`RuntimeSnapshot`'s new
`"audio_context"`/`"caption"` fields and the Visual Inspector panel.

**Fourth follow-up milestone (Handler -> Physical Source Resolution,
also folded into `AUDIO_CONTEXT_RESOLUTION.md`)**: closed the one gap
the third milestone had explicitly left open. What looked like a
2-level dispatch to "two different handler functions" turned out, on
full disassembly, to be a 2-level lookup into a literal, static, embedded
filename string table -- there was no handler function to trace into.
`table1`'s byte is the XAPACK file number directly. Initially validated
for only 9 entries (0-8); a follow-up live check (Phase 5, below) found
the real table actually spans the disc's full 43 files (00-42), catching
and fixing a real bug where a valid selector resolving to file 9 was
wrongly reported as unresolved. Live-validated for real selectors 25,
26, and 28, cross-checked against the completely independent
LBA-position-based resolver via `cross_validate_source()` -- all agree
exactly. Test count: **478 passed** (452 + 26).

**Fifth follow-up milestone (XA File Open / Stream Resolution,
`XA_STREAM_RESOLUTION.md`)**: traced past the resolved filename toward
the actual file-open call. Found the filename gets built into a real,
live-readable ISO9660 path string (`"\DAT\XA1\XAPACK09.BIN;1"`, complete
with the standard `;1` version suffix) at a fixed address -- a THIRD
independent confirmation of the resolved file. The actual file-open
consumer itself is a genuine, honestly-reported blocker: two systematic
searches (absolute address construction, `$gp`-relative small-data
access) both found zero consumers across ~576KB of loaded code. Separately,
found and confirmed a real "event start LBA" field in an adjacent
structure (`0x800A61A8` -> `0x800A60EC+0x04`), matching the real disc
catalog exactly for two different files -- genuine progress on event
boundaries despite the file-open blocker. All three independent
resolution mechanisms (position-based, selector-table-based,
descriptor-structure-based) now cross-validate exactly on live capture.
Also fixed the real bug this pass's own investigation surfaced in
`gcrts.audio_context` (the too-narrow 0-8 cap). Test count: **492
passed** (478 + 14: 7 in `test_audio_stream_source.py`, 6 in
`test_xa_disc_index.py`'s new `resolve_filename_to_path` coverage, net
+1 elsewhere).

**Sixth follow-up milestone (XA Channel / Filter Runtime Resolution,
`XA_STREAM_RESOLUTION.md`'s own follow-up section, `gcrts.cdrom_driver_map`)**:
pursued the file-open blocker from a different angle -- CD-ROM
filter/channel runtime state instead of a third filename-consumer scan.
A live hardware write watchpoint on the CD-ROM controller's MMIO block
(`0x1F801800`-`0x1F801803`) caught real writes from this game's own RAM
code within seconds, and reading the pointer-variable table those writes
go through gave an exact, byte-for-byte match to the real PS1 CD-ROM
hardware register map (`0x800A30BC`/`C0`/`C4`/`C8` -> the 4 real
registers) -- explaining, architecturally, why the earlier
filename-consumer scans found nothing (this game's addressing style
loads a pointer once from a small RAM variable rather than constructing
addresses inline, invisible to an adjacency scan). The shared "issue one
CD-ROM command" routine was located (`0x80081C00`), and the real,
publicly-documented Setfilter command number (`0x0D`, LibPSn00b/psx-spx:
"Sets XA audio filter", 2 params) was confirmed against public sources.
Separately, `0x800A61B0` (Stage C's own "a pointer... not identified
yet") is now confirmed to be a real BIOS event descriptor
(`OpenEvent`/`EnableEvent`/`DisableEvent`, matching the public
`F1000000h`+ descriptor range exactly); its third dispatch branch
(`0x80077d78`) was fully decoded and found to be PS1 Root Counter
(Timer) setup, not CD/XA -- ruled out honestly, not left ambiguous.
**Three separate live attempts to catch the command routine actually
firing with `0x0D` found zero hits** -- a real, reported blocker,
narrower in kind than before (the mechanism and protocol are now known;
only the one live observation is still missing). `xa_channel` remains
`POSITIONAL_UNCONFIRMED`. Test count: **497 passed** (492 + 5 in
`test_cdrom_driver_map.py`).

**Seventh follow-up milestone (Capture the Real CD-XA Setfilter Command,
`XA_STREAM_RESOLUTION.md`'s own follow-up section, `gcrts.cdrom_setfilter`)**:
closed the final gap -- a real, live Setfilter call with actual
file/channel values. The previous milestone's zero-hit result turned
out to hide a real bug: the breakpointed address read the command byte
from the wrong stack offset (`sp+0x11` instead of the real `sp+0x12`),
silently returning a plausible-but-wrong `0x00` (Sync) across three
full live sessions, including two real voiced segments playing. A
static scan for every genuine command-register write site (not a
repeat of the same live-capture technique) found the real call sites
and proved the command byte sits in `$v0` directly, no stack-offset
guessing needed. Breakpointing those found real Setfilter traffic
within seconds: **file=2, channel=1**, reproduced byte-identical on a
second independent capture, with `file=2` cross-validated against the
real disc catalog (`XAPACK02.BIN`, a real file). Honestly scoped: no
simultaneous LBA cross-check was taken at the exact capture instant, so
this is live-captured and reproduced, not triple-cross-validated the
way the selector-table chain is. This required an actual live
breakpoint session (not passive polling, unlike every other resolver
in this stack) -- documented as a historical record
(`KNOWN_SETFILTER_OBSERVATIONS`), the same pattern
`KNOWN_CUE_SOURCES` already established. Test count: **506 passed**
(497 + 9 in `test_cdrom_setfilter.py`).

## Starting point

Stage C (`BACKLOG_INVESTIGATION_RESULTS.md`) had already live-traced one
complete chain, every link captured, none inferred:

```
script sound_or_voice_cue (0x0800, param=127)
  -> 0x800760b4 (writes raw params to 0x800a6114-17)
  -> 0x80077808 (dispatches on category==2)
  -> 0x80080d54 (BCD MSF-to-LBA: MSF 28:14:21 -> LBA 126921)
  -> DAT/XA1/XAPACK08.BIN, channel 7, mono 4-bit XA-ADPCM
```

What that trace never established: *when* playback actually starts,
whether it's *currently* playing, *where* it is within the stream, and
*when* it stops. That's this milestone's scope.

## What is CONFIRMED (live-verified this session)

**A real three-state lifecycle**, keyed off `0x800A6107` -- the *second*
byte of the "state pair" Stage C had already found being written but
never correlated with playback activity over time:

| Raw byte | Lifecycle state | Live evidence |
|---|---|---|
| `0x00` | STARTING | Observed only transiently, at the instant a save state carrying a fresh dispatch loads, and again for ~14s immediately after a fresh cue's `last_req_params` was written but before the position counter started moving. |
| `0x01` | PLAYING | Sustained for 37+ real seconds in one poll, 47+ in a live end-to-end run using the actual module -- always co-occurring with the position counter (below) advancing, and with `0x800A6114`'s raw params holding a real, nonzero cue value. |
| `0x02` | STOPPED | Sustained for **57+ consecutive real seconds** with zero movement in one dedicated poll, and independently reconfirmed in the end-to-end run -- always co-occurring with `0x800A6114` cleared to `0x00000000` and the position counter completely frozen. |

Two independent signals agreeing (`0x800A6107`'s value AND
`0x800A6114`'s clear-to-zero) is what makes STOPPED detection solid, not
a single byte's say-so -- `capture_audio_event` explicitly downgrades a
`0x02`+nonzero-params combination to `UNKNOWN` rather than trusting a
never-observed-live combination (see `tests/test_runtime_audio.py::
test_capture_reports_unknown_when_stopped_state_disagrees_with_params`).

**A real, live-verified positive-path proof**, captured by pausing on a
reload of save-state slot 3 and immediately snapshotting:

```
event: script_parameter=127, state=STARTING, confidence=STATIC_LOOKUP
       source_file=DAT/XA1/XAPACK08.BIN, xa_channel=7, start_lba=126921
       position_counter=128044
snapshot.active_audio == [that event, as a dict]
```

**A real, live-verified negative-path proof**, minutes later once the
scene had genuinely finished: `capture_audio_event` returns
`state=STOPPED`, and `capture_runtime_snapshot` correctly reports
`active_audio == []` -- stale finished audio is never reported as
currently active.

**Position genuinely tracks progress**, not just a fixed clock:
`0x800A61AC` (already known from Stage C as the address `0x80080d54`'s
MSF-to-LBA result is stored into) was polled every ~0.6-0.8s across two
independent sessions. While state was PLAYING it increased on almost
every poll, including real multi-second plateaus (consistent with
natural speech pauses -- a fixed-rate timer would never plateau); while
state was STOPPED it was completely static for 57+ seconds straight.

**Multi-cue scenes are handled correctly, confirmed live, not just in
theory**: during the Phase 7 end-to-end run, the dispatched cue actually
changed mid-scene (`script_parameter` 127 -> 126) and the position
counter genuinely reset lower at that exact moment. `capture_audio_event`
already had a rule for this (`position_counter_start` only carries
forward across polls when `script_parameter` is unchanged) written
*before* this specific transition was observed, and the live trace
confirmed it fires correctly, not just in the unit tests that inspired
it.

## What is PARTIAL / not confirmed -- do not overclaim these

- **`0x800A61AC`'s exact real-time unit.** ITS MECHANISM is now
  explained (see `AUDIO_CUE_RESOLUTION.md`, Observation 1): it advances
  because the confirmed dispatch site calls `0x80080d54` repeatedly
  (~6x/second) while a cue is active, each call computing a slightly
  larger LBA than the last and overwriting this address with the fresh
  result -- not a separately-incrementing counter. What is still NOT
  confirmed is why the climb rate (~100-300/sec across sessions) doesn't
  cleanly match a simple real-time-to-sectors conversion; treat
  `position_counter` as a real, live, generally-non-decreasing progress
  signal useful for source resolution (see below) and for detecting
  "is this actively changing right now," not as a calibrated
  millisecond value.
- **`playback_offset_ms`.** Deliberately NOT derived from
  `position_counter`'s own scale. `compute_playback_offset_ms` instead
  sums real wall-clock time across consecutive polls where state stayed
  PLAYING for the same `script_parameter` -- accurate to normal polling
  latency, but only as fine-grained as the caller's own poll cadence,
  and reset to `None`-contributing whenever a gap includes a
  non-PLAYING sample. This remains the right choice, not a stopgap --
  see `AUDIO_CUE_RESOLUTION.md` for why calibrating the counter itself
  turned out to be the wrong direction entirely.
- **Segment/cue-reset semantics.** `AUDIO_CUE_RESOLUTION.md`
  (Observation 2) found something more surprising than a simple reset
  rule: the SAME raw `script_parameter` (127) resolved to two
  *different physical files* across independent real-time captures of
  the identical save state. The determining factor tracks real elapsed
  time since the state loaded, not script position. This means
  `position_counter`'s resets are not simply "one reset per new cue" --
  do not assume that.
- **`source_file`/`xa_channel` resolution.** Superseded design, see
  `AUDIO_CUE_RESOLUTION.md` -- `capture_audio_event` now resolves
  `source_file` LIVE from the observed LBA against the disc's real,
  exact file table (general, not a per-cue guess), falling back to the
  historical `KNOWN_CUE_SOURCES` table only when that fails.
  `xa_channel` is still computed but confirmed to be a positional
  artifact of the disc's 8-way interleave, not proven to reflect actual
  SPU channel selection -- reported under
  `AudioConfidence.POSITIONAL_UNCONFIRMED`, not silently upgraded.
- **PAUSED** is a real enum value (kept for future evidence / other
  audio categories -- music/SFX/ambient may behave differently) but was
  never observed live this session. **REQUESTED** likewise has no
  independently-observed raw value distinct from STARTING's transient
  `0x00` -- it's kept as a conceptual pre-dispatch state per the
  original call-chain trace (`0x800760b4` writes params *before*
  `0x80077808` even runs), not because a separate raw byte was caught
  for it specifically.

## What is UNKNOWN

- Why `0x800A6106` (the byte the pre-existing getter `0x80076118` reads)
  never changed from `0x00` across every observation this session, while
  `0x800A6107` -- one byte over -- carries all the real lifecycle
  information. (An early version of this module actually mis-read the
  two bytes as a single little-endian `u16`, which matched neither
  byte's real value and silently produced `UNKNOWN` for every event --
  caught by testing the model against live memory before trusting it,
  not by code review. See the module's own docstring.)
- Whether music/SFX/ambient categories (this game's own
  `0x80077928`-dispatch categories other than `2`) share this exact
  state machine at all, or have their own.
- Whether a general, static `cue -> descriptor` lookup table/function
  exists anywhere in RAM or in an executable at all. Given the same raw
  parameter value was found meaning different things at different real
  times (`AUDIO_CUE_RESOLUTION.md`, Observation 2), the more likely
  explanation is that `script_parameter` is a small, reused/recycled
  index whose real meaning depends on script execution position -- a
  question outside this RAM-polling tracker's reach without a parallel
  live script-buffer correlation, not attempted this pass.

## How to reproduce

Load save-state slot 3 (the same dialogue scene Stage C's original trace
used) via the PCSX-Redux Web API (`/api/v1/state/load?slot=3`), then:

```python
from gcrts.live_extract import GdbClient
from gcrts.runtime_audio import capture_audio_event

c = GdbClient(port=3334, timeout=10)
event = capture_audio_event(c.read_memory)
print(event)
c.close()
```

Or through the production path (no manual GDB at all):

```python
from gcrts.runtime_visual_provider import RuntimeVisualProvider
from gcrts.runtime_snapshot import capture_runtime_snapshot

provider = RuntimeVisualProvider(projects=[])
frame, objects = provider.scan()
snapshot = capture_runtime_snapshot(provider, frame, objects)
print(snapshot.active_audio)  # [] once the cue has stopped
```

## Definition of Done -- honest accounting

| Question | Status |
|---|---|
| What audio is playing? | PARTIAL -- `script_parameter` is captured live and reliably, but is NOT a stable source identifier by itself (see `AUDIO_CUE_RESOLUTION.md`) |
| Where did it come from? | CONFIRMED, generally -- resolved live from the observed LBA against the disc's own exact file table (`gcrts.xa_disc_index.resolve_lba_to_file`), for any position actually seen, not just cue 127 |
| Which XA channel is active? | PARTIAL -- a real value is computed, confirmed to be a positional artifact of the disc's interleaving, not proven to reflect true SPU channel selection |
| When did it start? | CONFIRMED (raw state transition to `0x00`/STARTING, live-observed) |
| How far into it are we? | PARTIAL -- a real, live, actively-changing signal exists (`position_counter`, now explained as repeated MSF-to-LBA recomputation, `AUDIO_CUE_RESOLUTION.md`); its exact real-time unit/scale is not confirmed |
| Is it still playing? | CONFIRMED (`state == PLAYING`, cross-checked against position advancing) |
| When did it stop? | CONFIRMED (raw state transition to `0x02`/STOPPED, cross-checked against params clearing and position freezing, sustained 57+s) |
| Preserved in a paused `RuntimeSnapshot`? | CONFIRMED -- live-verified: an active event is captured and included; a stopped one is correctly excluded |

## Explicitly not built this pass

Per the milestone's own scope: no waveform editor, no audio extraction
UI, no subtitle editor/rendering, no movie runtime tracking, no full
audio-bank (`PROGHEAD.CDB`/`PROGVAB.CDB`) parser, no SDB work, no
Renderer 2 research, no real-hardware disc validation.

## Recommended next milestone

Extend `KNOWN_CUE_SOURCES` by tracing 2-3 more cues the same way Stage C
traced 127 (the 126 caught live this session during Phase 7 is a ready-
made, already-observed candidate) -- this turns the current one-entry
proof of concept into believable general coverage, and would also be the
natural place to finally pin down `0x800A61AC`'s real unit (comparing
several cues' position-counter behavior against their own known
start LBAs and durations is a much stronger basis for that than one
sample). Movie/subtitle work should stay blocked behind Stage B's own
still-open "which overlay is actually resident during movie playback"
question, unchanged by this milestone.
