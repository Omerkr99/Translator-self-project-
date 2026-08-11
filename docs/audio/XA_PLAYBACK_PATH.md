# Locate the Real XA-ADPCM Playback Path

Goal: capture a real `ReadS` (`0x1B`) command and trace backward to the
game's actual XA-audio setup path.

## Headline result

**`ReadS` was not captured — but a second live session ruled out one
of the two structurally possible explanations for the audio the user
hears, with decisive evidence.** New module: `gcrts/xa_playback_path.py`.

## Audible test event

A second real, live session: instrumentation armed on the current live
game state, save slot 9 (a known pre-voiced-segment point) reloaded
while capture stayed armed, and the user confirmed the audio segment
triggered. ~230+ real seconds of continuous command capture through
that trigger.

## ReadS

**Not captured.** Zero occurrences across this entire session, on top
of zero occurrences across the previous milestone's ~460-second
session — two independent real sessions, both spanning confirmed
audible playback, neither ever producing `0x1B`.

## Hardware writer

Not found — there is nothing to trace backward from.

## Setmode

Unchanged from `AUDIO_PLAYBACK_TRUTH.md`: the only real value ever
captured is `0x01` (CDDA bit only; XA-ADPCM and XA-Filter both off).
The exact same non-audio cycle repeated throughout this session's
trigger, with no structural change at the moment of the reported
trigger.

## Setfilter

Unchanged: `(2, 1)`, still not tied to this or any specific event.

## Sector evidence

Not gathered this pass — no confirmed XA-audio stream exists yet to
compare sectors against.

## Playback start / end

Not identified — gated on finding the real path.

## The decisive new finding: CD-DA is structurally impossible on this disc

The milestone's own required fallback list included "the game uses
CDDA for the audible content being tested" as a hypothesis to check
before continuing to force an XA-ADPCM model. Checked directly against
the real disc image's own `.cue` file:

```
FILE "Twilight Syndrome - Tansaku Hen (Japan).bin" BINARY
  TRACK 01 MODE2/2352
    INDEX 01 00:00:00
```

**Exactly one track, in the standard PS1 MODE2/2352 data-sector
format.** There is no separate Red Book CD-DA audio track anywhere on
this disc — genuine CD-DA playback is not just unobserved, it is
physically impossible for this game. This decisively rules out
hypothesis 6, and by elimination strengthens hypothesis 1 (the audible
content, whatever configures it, is very likely XA-ADPCM after all,
since it's the only real PS1 audio mechanism left standing) while
leaving hypotheses 2/4/5 (a different command/path, an incomplete
observation point, or a BIOS-side path) as the genuinely open
questions. See `gcrts.xa_playback_path.PLAYBACK_PATH_HYPOTHESES` for
the full evaluation table, all 6 entries, each with its real evidence
(or explicit lack of it) attached.

## New playback model

No change to `gcrts.audio_playback_truth.AudiblePlaybackState` (still
just `UNKNOWN`) — this pass narrowed the search space (ruled out CD-DA,
reconfirmed `ReadS` is never issued through the 3 known command sites)
without finding a working replacement signal.

## Old path status

`gcrts.xa_playback_path.OLD_READN_CYCLE_STATUS = "RULED_OUT_AS_XA_AUDIO_PATH"` —
a permanent classification now, backed by two independent lines of
evidence (the Setmode bit decode, and two separate confirmed-audible
sessions producing zero `ReadS`).

## Extraction readiness

Unchanged: still blocked on the same unresolved question this
narrowed but did not close.

## Tests

7 new tests in `tests/test_xa_playback_path.py`, including a regression
guard that no hypothesis can be silently marked resolved without a real
evidence string attached.

## Remaining blocker before Audio Inspector

The real audio-configuring code path is not reachable through either
of the two static-scan strategies (narrow or wide window) this project
has tried against the 3 known command-write sites' addressing pattern.

## Next milestone

Given `READS_EVER_OBSERVED = False` even under direct, confirmed-
audible test conditions, and CD-DA now ruled out: search for a SECOND,
independent CD-ROM command-register pointer-variable set (a different
fixed address than `0x800A30C0`, potentially belonging to a separate
"audio driver" instance) rather than repeating the same hunt through
the already-exhausted 3 sites.
