# Real Audio Playback Truth

Goal: identify the real runtime signal(s) that correspond to audible
XA playback, and rebuild the `RuntimeAudioEvent` lifecycle around
evidence that actually tracks what the user hears — not
`0x800A6107`, which the previous milestone (`CDROM_SETFILTER_CAPTURE.md`)
proved stayed `STOPPED` throughout a confirmed-audible ~460-second
session.

## Headline result

**The disproof stands confirmed; no replacement signal was found this
pass.** Two independent investigation strategies both came back
negative for a genuine XA-audio-configuring command path reachable
through the code this project has already mapped. This is reported
honestly, per this project's own standing discipline, rather than
forcing a plausible-but-unverified `AUDIBLE_XA` state into existence.
New module: `gcrts/audio_playback_truth.py`.

## `0x800A6107`

Reclassified, not deleted. `gcrts.runtime_audio.AudioLifecycleState`'s
`PLAYING`/`STOPPED` docstrings and class-level docstring now explicitly
say what's actually proven: these values correlate with *some* real
playback session (the original, separate live observation that found
them), but are **not confirmed general** — a later session with
confirmed real audible playback throughout never left `STOPPED`. Its
real role remains genuinely `UNKNOWN`
(`gcrts.audio_playback_truth.raw_engine_state_meaning()` → `"UNKNOWN"`).
The enum values themselves were kept (per this milestone's own Phase 1
instruction not to delete the field) — only their documented meaning
changed.

## Audible positive control

The prior milestone's ~460-second session (user directly confirmed
hearing real audio) is the audible positive control reused here. Its
real, decoded `Setmode` value (`0x01`) turned out to be the single most
important piece of new evidence this pass:

Per public PS1 documentation (psx-spx), Setmode's bits are:

| Bit | Meaning |
|---|---|
| 7 | Speed (0=normal, 1=double) |
| 6 | **XA-ADPCM** (0=off, 1=send XA-ADPCM sectors to SPU) |
| 5 | Sector Size |
| 4 | Ignore |
| 3 | **XA-Filter** (0=off, 1=only sectors matching Setfilter) |
| 2 | Report |
| 1 | AutoPause |
| 0 | CDDA |

`0x01` = **only bit 0 (CDDA) set. Bits 6 and 3 are both OFF.** This
means the entire repeating `Setloc → Setmode → ReadN → Pause →
Setfilter(2,1)` cycle this project has now captured across three
separate milestones is **not configured to route XA-ADPCM sectors to
the SPU, and Setfilter has no effect on it** (XA-Filter is off). This
is decisive: that cycle was never the audio path. It fully explains
why nothing about it ever correlated with anything — it's most likely
a plain data-read loop (e.g. script/resource streaming) that happens
to share the same low-level "issue one CD command" infrastructure.

## Silent negative control

Not captured as a separate, deliberately-silent session this pass —
the Setmode finding above made a positive/negative comparison
unnecessary to reach a decisive conclusion (a `0x01` value is
definitionally not an XA-audio configuration, regardless of what
else is or isn't happening at the same time).

## CD command behavior

Per public PS1 documentation, the command that actually plays XA-ADPCM
sectors is **`ReadS` (`0x1B`)**, not `ReadN` (`0x06`, a plain data
read). **`0x1B` has never appeared in any capture this project has
taken, across every milestone.** All `ReadN` observations decode to the
non-audio Setmode above.

## Setmode

Exact value: `0x01`. Documented meaning: CDDA-only, XA-ADPCM and
XA-Filter both off. Live context: observed identically across every
occurrence in the repeating command cycle traced this session and the
previous one. Confidence: `LIVE_CAPTURED` for the raw byte (real,
reproduced), decisive for ruling out this cycle as the audio path.

## Interrupt/DMA evidence

Not investigated further this pass (Phases 8–9 were deprioritized in
favor of the higher-leverage Setmode/ReadS analysis, which already
produced a decisive result). Real CD-ROM interrupt activity was already
confirmed happening constantly in earlier milestones
(`XA_STREAM_RESOLUTION.md`'s hardware watchpoint tests); this pass adds
no new interrupt-source-level detail.

## New playback state

`gcrts.audio_playback_truth.AudiblePlaybackState` exists with exactly
one member, `UNKNOWN` — deliberately. A regression test
(`test_audible_playback_state_has_no_confirmed_states_yet`) pins this
down specifically so a future pass can't quietly add an unverified
`AUDIBLE_XA` value.

## A widened search for the real command site (also negative)

The original static scan (three milestones ago) that found the 3
confirmed command-write sites searched up to 12 instructions past each
load of the command-register pointer. This pass widened that to 60
instructions and found 4 additional raw hits — but direct disassembly
of each showed they were **false positives** (the same-numbered
register reloaded with a *different*, closer pointer between the
original load and the store) or already-known parameter/request writes
belonging to the 3 already-confirmed sites. **No new genuine
command-issuing site, and no `ReadS`, was found this way either.**

One real, non-audio finding came out of this: the `0x80081AC8` site
(previously observed carrying undocumented values `0x7F`/`0x80`) is a
generic "send a 4-byte command struct" helper — writes
`struct[0]→param, struct[1]→request, 3→index, struct[2]→command,
struct[3]→param, 0x20→request`, the same architectural pattern this
project found much earlier for `0x80077808`. This strongly suggests the
helper is reused by more than one caller for more than one purpose, and
`struct[2]` (what this project's captures read as "the command byte")
is only a genuine CD-ROM command number for *some* of those callers —
not necessarily the ones that produced `0x7F`/`0x80`. Not resolved
further; reported as observed, not assigned an invented meaning.

## Setfilter scope

Unchanged from `CDROM_SETFILTER_CAPTURE.md`: `filter_appears_persistent()`
remains `True`. This pass adds one clarification: since the cycle
Setfilter(2,1) appears in has XA-Filter *disabled* in its own Setmode
call, that specific Setfilter's persistence may not even matter
functionally for that cycle — reinforcing that it's very unlikely to be
the real audio-selecting mechanism, consistent with (not contradicting)
the "not proven event-specific" finding.

## Event boundaries

No improvement — still gated on finding the real audio-configuring
code path, which this pass did not find.

## Extraction readiness

Unchanged: still requires an explicitly-supplied, event-specific
channel that this project has not yet located.

## Tests

6 new tests in `tests/test_audio_playback_truth.py`.

## Honest assessment against the Definition of Done

The milestone's own Definition of Done required distinguishing "the
old engine byte says 0x02" from "the game is actually streaming
audible XA audio right now" using live-confirmed evidence. This pass
achieved the first half decisively (the old byte is now correctly
demoted, with real evidence) but not the second (no working
`AUDIBLE_XA` detector exists). Per the milestone's own explicit
instruction to correct the model when evidence requires it rather than
force a result: this is reported as a genuine, real, unresolved
question, with two now-eliminated wrong turns (the `0x800A6107` byte,
and the traced `ReadN`/Setmode/Setfilter cycle) narrowing the search
space for whoever picks this up next.
