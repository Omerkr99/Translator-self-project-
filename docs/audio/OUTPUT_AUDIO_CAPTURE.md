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
