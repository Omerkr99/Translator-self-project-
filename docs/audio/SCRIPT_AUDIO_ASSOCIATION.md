# Script Context ↔ Audio Dispatch Correlation

Follow-up to `AUDIO_CUE_RESOLUTION.md`, which found that the raw
`sound_or_voice_cue` script parameter is not a stable physical-source
identity — the same value (127) resolved to different `XAPACK*.BIN`
files at different real times, with no explanation at that point beyond
"depends on real elapsed time since the state loaded." This milestone
finds and proves the actual explanation, and builds the machinery to use
it: new module `gcrts/script_audio_association.py`.

## Headline result

**The script buffer itself gets refreshed with new content between
dialogue moments, and different refreshed loads can coincidentally share
the same structural shape** (a `sound_or_voice_cue` at word offset 1
with parameter 127) while containing genuinely different dialogue. A
content-based fingerprint of the owning script unit — not its position,
not the raw parameter — cleanly distinguishes them and correlates
exactly with which physical audio file gets used.

## What was already known going in

- `0x800A4CEA` is a live-confirmed script cursor: a 16-bit word-index
  into the buffer at `SCRIPT_BUF_ADDR` (`0x801FE800`), fully traced by a
  prior session (`DECODER_READ_CURSOR.md`) from the decoder's own entry
  to its actual word-consumption instruction — not a guess.
- `gcrts.script_unit.units_from_script_document` already segments a
  decoded script buffer into `ScriptUnit`s with exact, gapless word-
  offset boundaries (segmented at pause-flag control codes — a real
  "one displayed line, waiting for input" boundary, not arbitrary).
- `DECODER_READ_CURSOR.md` itself already flagged, as an open question,
  that "the live script buffer... appears to be refreshed/rewritten as
  the game streams new content in, likely in chunks smaller than a
  whole scene." This milestone found direct, concrete proof of exactly
  that, and turned it into a design constraint rather than leaving it
  as a caveat.

## Live proof

Four samples, ~14 real seconds apart, same save state (slot 3), same
polling-only capture technique used throughout this project (no
breakpoints — this session's own `AUDIO_CUE_RESOLUTION.md` already
found breakpoint overhead measurably distorts this exact game's timing):

| Sample | t | script word offset | raw param | `buffer_fingerprint` | resolved file | LBA |
|---|---|---|---|---|---|---|
| 0 | +0s | 1 | 127 | `48564b3b92d8` | `XAPACK08.BIN` | 129041 |
| 1 | +14s | 1 | 127 | `48564b3b92d8` | `XAPACK08.BIN` | 129551 |
| 2 | +28s | 1 | 127 | `11ccf57850d3` | `XAPACK06.BIN` | 117203 |
| 3 | +42s | 1 | 127 | `11ccf57850d3` | `XAPACK06.BIN` | 118883 |

Word offset and raw parameter are **identical across all four samples**
— exactly the ambiguity `AUDIO_CUE_RESOLUTION.md` left open. The
fingerprint (a hash of the owning `ScriptUnit`'s own decoded content,
`gcrts.script_audio_association._fingerprint_unit`) changes exactly
once, between samples 1 and 2, and tracks the resolved file exactly:
same fingerprint → same file, different fingerprint → different file,
with 100% consistency across this sample set. This is not a coincidence
of small numbers — the LBA drift *within* each fingerprint group also
matches the already-understood mechanism (`AUDIO_CUE_RESOLUTION.md`
Observation 1: the confirmed dispatch site recomputes a slightly larger
LBA on each of several calls per second while a cue is active).

Live-verified independently a second time through the full production
path (`RuntimeVisualProvider` → `RuntimeSnapshot`, via the Web API's
bulk RAM dump rather than a direct GDB read): the same fingerprint
(`48564b3b92d8`) reappeared for the same real dialogue content, with
real, correctly-decoded Japanese dialogue text attached
(`ScriptAudioAssociation.dialogue_text`).

## What this explains

Answers `AUDIO_CUE_RESOLUTION.md`'s own open research question directly:
the same raw parameter value resolving to different files is not a
mystery in the sense of "the game does something exotic with `127`" —
it's simply that `127` is a common/reused value across genuinely
different lines (plausible explanations not further pursued this pass:
a default/frequently-used speed or volume-adjacent parameter, or simply
a common small index within whatever per-scene structure assigns these
values), and the buffer holding the ACTUAL line changes underneath the
cue's own coincidentally-identical shape. Word offset and raw parameter
were never going to be stable identity on their own; content is.

## What this does NOT explain (left open, not guessed at)

- ~~The exact mechanism that decides which physical file/position a
  given script occurrence's `0x80080d54` calls will target~~ — **now
  resolved, see `AUDIO_CONTEXT_RESOLUTION.md`.** The real selector was
  never the "127" inline parameter this document tracks — it's the
  `sound_or_voice_cue` control word's own low byte, a value this
  document's own `ScriptCode.raw` had all along but nothing had
  separately examined until the very next milestone.
- Whether the buffer-refresh boundary aligns with `ScriptUnit`
  boundaries, scene boundaries, or something else entirely — only
  observed that a refresh happened between two real capture moments,
  not precisely when or why.
- General coverage: this was proven for the one control code
  (`sound_or_voice_cue`, subtype `0x0800`) already known end-to-end from
  Stage C/`AUDIO_CUE_RESOLUTION.md`. Other control codes near a sound
  cue (candidates the original brief named: XA/AWAIT/RUN/SEC/FLG/ACT-
  style commands from the external fan-toolkit's own decoder) were not
  inspected this pass — a real, scoped-out piece of future work, not
  silently assumed irrelevant.

## Design notes

- `ScriptAudioAssociation.stable_key` is the actual deliverable identity:
  `{script_source}/{script_unit_id}/offset_{control_code_offset:#x}/{buffer_fingerprint}`.
  Deliberately NOT a RAM address (this project's own established lesson,
  reused here: overlays and, now confirmed, the script buffer itself can
  move/refresh) and NOT the raw parameter alone (proven unstable).
- `RawCueParameter` (the script's own inline value), `ScriptControlOccurrence`
  (a specific word-offset in a specific buffer load, i.e. what
  `find_owning_sound_cue` returns), `RuntimeAudioEvent` (the lifecycle
  state machine from the prior milestone), and the physical `AudioAsset`
  (`source_file`/`xa_channel` from `AUDIO_CUE_RESOLUTION.md`'s resolver)
  are kept as genuinely separate concepts throughout, per the brief's
  own instruction — `ScriptAudioAssociation` is the join between them,
  not a replacement for any of them.
- Repeated low-level `0x80080d54` calls while one cue stays PLAYING are
  correctly treated as ONE logical event, not one per call: association
  is built from `capture_audio_event`'s own already-deduplicated
  `RuntimeAudioEvent` (which already tracks `position_counter_start`
  across a contiguous PLAYING span), not from raw dispatch calls
  directly — no new grouping logic was needed because the prior
  milestone's lifecycle tracking already did this correctly.
- `capture_script_audio_association` accepts an already-captured
  `audio_event` so a caller polling every cycle (like
  `RuntimeVisualProvider`) never fetches RAM twice for one logical
  snapshot moment — the same discipline every other live-capture module
  in this project already follows.

## Runtime integration

`RuntimeVisualProvider.last_script_association` (same caching pattern as
`last_audio_event`/`last_renderer1_validation`), computed once per
`scan()` right after the audio event. `RuntimeSnapshot.active_audio`
entries now include a nested `"script_context"` object when resolved —
never fabricated when it isn't. The Visual Inspector's read-only audio
panel shows the owning script unit, its offset, and a short dialogue
text preview alongside the existing state/source/position fields.

## Tests

14 new tests in `tests/test_script_audio_association.py`, including a
direct regression encoding of the exact live finding above (same offset
and parameter, different content, different fingerprint, different
`stable_key`). Full suite: 438 → **452 passed** (14 new), no
regressions.
