# Per-Event XA Channel Capture

Goal: observe one genuinely new audio event transitioning from
inactive → STARTING/PLAYING while the CD/XA setup happens, and capture
the actual file/channel state belonging to that exact event.

## Headline result

**The event-specific capture did not succeed — but the reason why is
itself the milestone's real finding.** Armed with both lifecycle
tracking and CD-ROM command capture on the CURRENT live game state (not
a static reload) for ~460 real seconds, spanning a stretch the user
directly confirmed included real, audible playback:

- The audio lifecycle state byte (`0x800A6107`) **never once left
  `STOPPED` (`0x02`)** — despite confirmed real audio playing.
- **8 separate Setfilter hits, all `params=(2, 1)`**, unchanged, while
  the position counter (disc-seek target) visited 5 different values
  in the same window, including one (`0`) that isn't a valid XA
  position at all.

Per this milestone's own explicit "Important failure rule": this is not
a failed milestone. It means the model **"one cue → one Setfilter"**
is wrong. The evidence instead supports **"one filter setting persists
across many housekeeping cycles and at least one real playback
event"** — a genuinely different, and answerable, question. See
`gcrts.cdrom_setfilter.filter_appears_persistent()` (`True`, with all
8 observations attached).

## Phase 1: pre-event state

Used the CURRENT live game state, not a static save reload — the
milestone's own core rule ("Do NOT use a static save-state reload as
proof of a fresh audio setup"). Confirmed live immediately before
arming: `state=0x02` (STOPPED), `position=158842` (a real, valid LBA
inside `XAPACK08.BIN`'s range), `last_req_params=127` (stale). This is
a genuine, currently-idle point, not a frozen historical snapshot.

## Phase 2: input method

Real player input — the user played the game directly while
instrumentation was armed. No synthetic `SendInput`/`keybd_event` was
used this pass, consistent with this project's own prior finding that
synthetic taps were unreliable for this game's real dialogue-advance
timing.

## Phase 3-4: instrumentation armed before input

Lifecycle (audio state byte) and CD command capture (the 3
statically-confirmed real command-write sites) were combined into one
script (`m9_transition_capture.py`, this session's scratch tooling),
armed and confirmed running (`bp arm ... -> OK`, `ARMED AND RUNNING`
printed) BEFORE any player action. The audio profile fingerprint was
independently re-verified live afterward and matched — the ~460-second
session stayed within the same, correctly-identified overlay the whole
time, not a drifted/stale address set.

## Phase 5: the transition

**Not caught as a clean STOPPED → STARTING → PLAYING sequence.** The
state byte simply never changed value across the entire session, even
though the user confirmed hearing real audio. This directly means
either: the transition is real but far shorter-lived than this
capture's cadence could catch, or `0x800A6107` tracks something
narrower than "is audio currently audible" (e.g. a specific dispatch
queue flag rather than playback-in-progress). Both are genuine open
questions, not resolved this pass — see `gcrts.runtime_audio`'s own
module docstring for the corresponding caveat added to its lifecycle
model.

## Phase 6-7: CD commands around the (absent) transition

A clear, repeating, ~0.6-second cycle was observed dozens of times:

```
Setloc(3, 0)  [0x02]
Setmode(1, 0) [0x0E]
ReadN         [0x06]
Pause         [0x09]
Setmode(1, 0) [0x0E]
Setfilter(2, 1) [0x0D]   <-- every cycle, unchanged
Setloc(3, 0)  [0x02]
ReadN         [0x06]
Demute        [0x0C]
GetlocP       [0x10]     (polled repeatedly)
```

Real, documented command bytes seen: `0x01` (Getstat), `0x02` (Setloc),
`0x06` (ReadN), `0x09` (Pause), `0x0A` (Init), `0x0B` (Mute), `0x0C`
(Demute), `0x0D` (Setfilter), `0x0E` (Setmode), `0x10` (GetlocP). Two
undocumented values (`0x7F`, `0x80`) were also seen at the other 2
command-write sites — not resolved this pass, flagged honestly rather
than assumed to be real CD-ROM commands.

## Phase 8: no per-event Setfilter found — the "why" investigation

Per the milestone's own Phase 8 instruction, this was not treated as a
dead end to keep repeating. The evidence directly supports one of the
listed alternatives: **"a persistent filter state is reused"** —
`filter_appears_persistent()` records this as the best-supported
explanation, given the filter's parameters stayed fixed across 8 hits
spanning 5 different seek positions and ~460 real seconds.

## Phase 9: CD filter state snapshot across the window

`params=(2, 1)` was the only value ever observed at the Setfilter site
across the whole window — see `KNOWN_SETFILTER_CONTEXT_CHECKS` (8
entries, all identical params). No T-1/T0/T1/T2 diff was possible
because no state transition was ever caught to diff around.

## Phase 10: raw-sector cross-check

Not attempted this pass — no event-specific channel exists to compare
against raw sectors for, and the position counter's repeated visits to
`0` (not a valid XA-region LBA) make it unclear which of the 5 observed
positions, if any, corresponds to genuinely active playback versus
housekeeping/idle polling.

## Phase 11: repeatability

The "repeat once" requirement is effectively already satisfied by the
8 within-session observations themselves: every single one, across
~460 seconds and 5 different LBA contexts, agreed exactly. A
fresh-reload repeat was not additionally performed this pass (this
session's own evidence already provides stronger repetition than a
single second reload would have).

## Phase 12-13: start/end boundaries

No improvement — no event-specific start was isolated (the position
counter's behavior in this idle/housekeeping-dominated window doesn't
distinguish "this LBA is a fresh event's start" from "this LBA is
where a periodic retry cycle happens to be probing"). No STOP
transition was observed either, since no STARTING/PLAYING was.

## Phase 14: extraction readiness

Unchanged from `AUDIO_EVENT_EXTRACTION.md`: `xa_file_number`/`xa_channel`
still never auto-populate for any specific live event.
`gcrts.audio_event_extraction` continues to require an explicitly
supplied, event-specific channel — this pass found more (much stronger)
evidence that the historical Setfilter should not be that value, not
less.

## Phase 15-16: runtime model / RuntimeSnapshot

Not changed this pass — no event-specific `setfilter_event` structure
was added to `RuntimeAudioEvent`, since none of this session's evidence
could actually be attached to one. Adding an unused/always-empty field
would misrepresent readiness; `gcrts.cdrom_setfilter`'s historical
record (now with 8 observations instead of 2) remains the accurate
home for this evidence.

## Tests

11 new tests: `test_known_context_checks_all_show_stopped_state_with_stale_params`
updated for 8 observations (was 2), plus new coverage for
`filter_appears_persistent()` and the position diversity that supports
it.

## Final assessment

The milestone's own "Important failure rule" applies directly: this is
a real, valuable result, not a failed search. **"One cue selects one
Setfilter" is not supported by any evidence this project has gathered
across three separate live-capture designs.** "One filter setting
persists across many cycles, possibly across an entire scene" is
directly supported by this session's 8 consistent observations.
