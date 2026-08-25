# Output Audio Capture: Resolving the Save-Slot-9 Line

The resolution to the multi-session question "which `AudioAsset` is the
save-slot-9 target dialogue line's real source" — reached by
sidestepping internal reverse-engineering entirely and capturing what
actually reaches the speakers.

## Why this pivot

Across this session, five independent internal-instrumentation angles
were each pursued to a real, disciplined conclusion, and none produced
a reliable `voice line -> source asset` mapping:

- CD-ROM command tracing (`Setloc`/`Setmode`/`ReadN`/`Pause` cycle,
  `ReadS` never observed).
- DMA tracing (channels 3/4 confirmed inactive).
- SPU MMIO tracing, including the SPU Sound RAM Transfer Address/Data
  FIFO write path — real writes found, but classified
  `SYSTEMIC_SPU_ACTIVITY` (the same `0x1000`/`0x707` pattern occurs
  identically at boot, before any dialogue is possible).
- Static + dynamic CD-ROM Data FIFO (`0x1F801802`) search inside
  `CAP0.EXE` — a real, address-order linear data-flow scanner
  (`gcrts.cdrom_fifo_scanner`) covering all 97,280 instructions found
  zero genuine reads of that register anywhere in the executable.
- Runtime profiling of `CAP0.EXE`'s own internal functions (a real
  statistical PC-sampling profiler, since 890 simultaneous exec
  breakpoints were found to slow the interpreter to a crawl) — the
  top target-window-specific candidates all resolved to generic
  UI/rendering code (an RLE decompressor into a shared, already-ruled-out
  scratch buffer; a GTE 3D-matrix loader; a bitmask utility).

Each of these is real, disciplined, negative evidence — not a dead
end from lack of trying. The governing realization: **the bottleneck
was never identification** (the fingerprint matcher had already proven
itself, matching a real `XAPACK08:7` fragment back to itself at 0.945
similarity with the offset recovered to within 0.01s). The bottleneck
was acquiring a clean fragment of the actual audible line to feed it.

## The pipeline

```
PCSX-Redux's real digital audio output (WASAPI loopback, gcrts.output_audio_capture)
    -> target_full.wav (continuous capture spanning load -> dialogue -> after)
    -> RMS energy profiling (offline, no live capture needed) to localize the line
    -> target_tight.wav / target_context.wav (cropped excerpts)
    -> gcrts.audio_fingerprint (already-existing, already-validated matcher)
    -> sliding-window search with offset-continuity check
    -> candidate excerpt exported for direct human listening
    -> USER_VERIFIED
```

## Capture mechanism

`gcrts.output_audio_capture.record_loopback()` uses PyAudioWPatch (a
WASAPI-patched PyAudio fork) to open the real loopback device for the
default output ("Speaker (...) [Loopback]"), confirmed at 48000 Hz
stereo. This records the emulator's actual digital output — not a
microphone, not an inference from RAM — matching the milestone's own
governing principle: capture the exact sound that reached the speakers.

No PCSX-Redux built-in recording facility, Lua audio-output API, or
dedicated GUI recording widget was found (checked directly against the
real upstream source: `src/core/spu.cc`, `src/core/pcsxffi.lua`,
`src/gui/widgets/` file listing) — loopback capture was the first
option in the preferred order that actually existed in this
environment.

## Localizing the line without live markers

A real capture ran with the user narrating "begin"/"end" verbally, but
without an in-band timestamp mechanism to record those markers
precisely. Rather than guessing, the line was localized from the
**audio's own acoustic shape**: a 0.5s-window RMS profile across the
full 90-second capture showed two long, steady high-energy stretches
(background music, t=1-10s and t=39-47s) bracketing a shorter, highly
irregular stretch (t=22-30s) — three distinct burst-pause-burst
clusters at 0.1s resolution, the shape of natural spoken phrasing, not
music. This matched the user's own placement ("early" in the session)
and gave `BEGIN≈22.4s, END≈30.5s` directly from the waveform, no
guessed timestamp needed.

## The offset-continuity test

A first attempt (matching the whole 8.6s tight crop as one query
against the full database) produced an apparently strong top score
(`XAPACK42:5`, 0.981) that turned out to be a **duration artifact** —
the top several "matches" were all fragments 0.16-1.6 seconds long,
far shorter than the query, so the matcher was sliding tiny clips
across a long, internally-varied candidate and finding coincidental
sub-window alignment. Restricting to duration-plausible assets did not
fully resolve this: the top candidate's reported offset was completely
unstable between the tight crop (67.94s) and the context crop (0.19s)
for the *same* underlying audio — a real match should not do that.

The real signal came from the sliding-window search
(`gcrts.audio_fingerprint.match_candidate` run repeatedly over 1.5s
windows, 0.25s hop, across `target_context.wav`): most windows showed
chaotic, incoherent top matches (a different asset nearly every
window, no offset progression) — a genuine negative result for those.
But `XAPACK22:7` showed **7 consecutive windows** (runtime t=7.50s to
9.00s) where the matched offset advanced from 2.34s to 3.84s — almost
exactly 1:1 with real elapsed time (each 0.25s step advancing the
asset offset by ~0.25s) — with consistently high similarity
(0.93-0.97), sharply distinct from the erratic behavior immediately
before and after. This is the "coherent offset progression" signature
this milestone's own brief specified as strong evidence, and it held
up under scrutiny (unlike the duration-artifact false lead above).

## Resolution

`XAPACK22:7` is the same asset originally confirmed via a completely
different method (a live LBA capture during a real dialogue trigger)
much earlier in this project's history, then explicitly retracted
2026-08-23 after a batch of fresh candidates were all rejected on
listening. This session's evidence is independent — a real captured
audio fragment, fingerprint-matched with offset continuity — and
converges on the same asset.

The user listened to the extracted candidate (first a partial excerpt
starting at the matched offset, missing the very beginning; then the
full asset from its own start once that gap was pointed out) and
explicitly confirmed both the content (a character saying "onee-chan"
preceded by a hand-washing sound effect) and the exact match. Persisted
via `gcrts.semantic_label_store.save_label` (`DIALOGUE`,
`USER_LISTENING`, `allow_overwrite=True` — the retraction history is
preserved in the notes field, not erased) and propagated into
`gcrts.dialogue_database` (`build_entry_from_asset` +
`save_entry`) — `semantic_confirmed: True`,
`semantic_verification_source: USER_LISTENING`.

## Tests

All 912 existing tests pass, no regressions. This session's live
capture/matching work was exploratory (real hardware, real audio, one
irreproducible-by-design session) rather than something to freeze into
a new automated test suite — consistent with this project's own
established convention for one-off live investigation sessions (see
`AUDIO_DATA_TRACE.md`'s own note on the same point).

## What's reusable going forward

- `gcrts.output_audio_capture.record_loopback()` — works for any future
  "capture what's actually audible" need, not specific to this one line.
- The RMS-profile localization technique (no live markers needed —
  the waveform's own shape finds the line).
- The offset-continuity sliding-window search as the standard
  discipline for validating a fingerprint match on a longer, mixed
  capture — a high top score alone is not sufficient evidence; a
  coherent, real-time-consistent offset across several adjacent
  windows is.

## Next

`XAPACK22:7` already has a Fandub template scaffolded
(`audio_export/fandub/XAPACK22_7/`) from earlier work — its workflow
status is `TRANSLATION_DRAFT`, now backed by a confirmed semantic
label instead of an unverified one. The same output-capture ->
fingerprint -> offset-continuity -> listen pipeline built here is
reusable for any other still-unverified save-slot line this project
returns to.

## Follow-up: generalization testing, and a genuine gap found

The method was formalized into `gcrts.output_audio_match` (pure,
independently-testable functions: energy-shape localization,
duration-plausible filtering, sliding-window search, offset-continuity
scoring/classification, plus a CLI) and then run against three more
independent lines, across two more save slots:

- `XAPACK20:4` (slot 7) — 0.96-0.98 similarity, 0.016s continuity error.
- `XAPACK08:3` (slot 9, a different line) — a genuinely short (~2s)
  line that only produced 2 consecutive sliding windows, below the
  classifier's own conservative 3-window threshold for
  `VOICE_ASSET_MATCH_FOUND` — a real, honest limitation for short
  lines, not a failure of the underlying match. Confirmed by direct
  listening despite the automated classifier calling it
  `NO_MATCH_IN_CURRENT_ASSET_DB`.
- One further attempt in a scene with continuous background music
  returned a genuine `NO_MATCH_IN_CURRENT_ASSET_DB` with zero coherent
  runs at all, even after trying an alternate manually-chosen window.
  This is the real boundary the method has hit so far: **RMS+ZCR
  fingerprinting struggles when dialogue is layered under continuous
  music/ambience**, not when the capture or localization is at fault.

## Follow-up: Live Scene Identification

Built `gcrts.live_scene_identification` to add a second,
overlay-independent evidence source: a direct VRAM screenshot via
PCSX-Redux's own Web API (`gcrts.screen_capture`, already existing
from earlier work), read directly (by a human or a multimodal model)
rather than through OCR. A first attempt to instead read the game's
internal script-cursor RAM address for deterministic scene tracking
was tried and abandoned once it was confirmed those addresses only
apply to `PROG.EXE`, not the `CAP*.EXE` family actually resident
during real gameplay (`identify_overlay()` confirmed `CAP1.EXE` active
at the time) — exactly the kind of overlay dependency this whole
pivot was meant to avoid.

A combined screenshot+audio capture on save slot 9 caught a chapter
title screen ("第二の噂 / 音楽室のM.F" — "The Second Rumor" / "Music
Room M.F.") at the same moment the audio pipeline found a strong,
continuity-validated match (`XAPACK13:6`, 3 windows, 0.956 similarity,
0.016s continuity error) — confirmed by direct listening. This is the
first case combining independent visual and audio evidence into one
`HIGH_CONFIDENCE` classification, per the confidence model below.

Two earlier capture attempts in this same session returned pure
silence and pure black frames for their entire 90-second windows — not
a bug, but the same PCSX-Redux focus-loss auto-pause behavior
documented much earlier in this project, confirmed by immediately
re-checking the same screenshot/audio mechanisms in isolation right
after (both worked instantly). Keeping the emulator window focused for
the capture's full duration is a real operational requirement, not
optional.

### Confidence model

`gcrts.live_scene_identification.classify_confidence()` never confirms
from one strong signal alone:

| State | Requires |
|---|---|
| `DETECTED` | Some capture exists; no strong signal yet |
| `CANDIDATE` | Fingerprint *or* continuity strong, not both |
| `HIGH_CONFIDENCE` | Fingerprint >= 0.9 *and* continuity >= 3 windows *and* independent visual context |
| `USER_VERIFIED` | A human listened and confirmed — always the final gate |
| `REJECTED` | No speech-shaped region found at all |

### Fast path: known candidates before the full database

`gcrts.output_audio_match.fast_match_with_known_candidates()` checks a
small set of already-confirmed assets first, and only falls back to
the full ~340-asset database if nothing strong turns up there — the
direct answer to "skip the full search when we already have relevant
information." The known set grows automatically as more lines get
`USER_LISTENING`-confirmed (`build_known_candidate_db()` pulls it
straight from `gcrts.semantic_label_store`). `gcrts.live_scene_
identification.identify_event_from_capture()` is the one-call,
streamlined version of the whole workflow (localize -> fast-match ->
continuity -> classify -> build the event record), reusing this fast
path automatically.

### Tests

30 new tests across `test_output_audio_match.py` and `test_live_
scene_identification.py` (fast-match hit/fallback behavior, the
orchestration function's REJECTED/DETECTED/HIGH_CONFIDENCE paths, all
synthetic). Full suite: 942 passed, no regressions.

### What's next

The gap is now precisely scoped: not another overlay or RAM address to
chase, but one layer to strengthen — extracting a confident voice
signal from a continuous music/ambience mix (progressively:
channel-split, mono-center mix, speech-band-pass filtering, spectral
fingerprints beyond RMS/ZCR, shorter sliding windows, multi-window
continuity, source separation only as a last resort), and letting
visual evidence (speaker, scene, visible text, known chapter) rank
audio candidates directly instead of requiring audio to carry the
whole identification alone.
