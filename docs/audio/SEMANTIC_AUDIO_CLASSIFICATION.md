# Semantic Audio Classification

A strategic pivot, directed by the user: stop treating "identify which
channel is dialogue" as a one-off question to guess at repeatedly, and
build a real **Audio Review Classification Pipeline** instead --
automation that narrows candidates, a human that makes the final call
in seconds by listening, and a permanent record so nothing is ever
re-guessed once confirmed.

## The four-layer model

Every piece of audio on the disc is now understood through four
deliberately separate layers, never conflated:

```
Source identity    -- ScriptUnit -> XAPACK -> channel   (gcrts.audio_asset_resolver)
Physical format     -- XA_ADPCM, sector layout, etc.     (gcrts.xapack)
Semantic role        -- what a channel actually CONTAINS  (gcrts.audio_semantic, this doc)
Product access       -- Play / Export / Translate / Replace (future UI layer)
```

Knowing the physical format (`XA_ADPCM`, confirmed and reference-decoder
verified) says nothing about whether a given channel holds dialogue,
music, ambience, or silence. That is the specific gap this milestone
closes.

## New modules

- **`gcrts/audio_semantic.py`** -- pure feature extraction
  (`compute_audio_features`: RMS envelope, silence ratio, burst
  count/duration, burst-length *regularity*, spectral centroid,
  zero-crossing rate) and relative, within-pack classification
  (`classify_candidate`, `rank_pack_channels`) that compares a channel
  against its own siblings in the same pack rather than fixed
  thresholds -- per the explicit instruction that "which channel
  deviates from the others" is stronger evidence than any absolute
  number. Every automated result carries `VerificationSource.HEURISTIC`
  and a numeric `candidate_score` -- **never** `CONFIRMED_DIALOGUE`.
- **`gcrts/semantic_label_store.py`** -- human-in-the-loop persistence.
  Once a person listens and confirms a label (or real runtime evidence
  confirms one), it's written to `audio_export/semantic_labels.json`
  and treated as authoritative from then on. Overwriting a confirmed
  label requires an explicit `allow_overwrite=True` -- deliberate
  friction against silent reclassification.
- **`gcrts/audio_review.py`** -- orchestration. `build_pack_review()`
  decodes every channel in a pack, computes features, ranks candidates,
  checks for any already-confirmed label, and writes a self-contained
  review folder: one `.wav` per channel, `analysis.json` (full
  machine-readable feature/classification record), `ranking.csv`
  (spreadsheet-friendly), and `review.html` (playable `<audio>` tags,
  an inline-SVG envelope plot per channel, classification badges, and
  any confirmed label surfaced prominently) -- built so a human can
  open one file and confirm a channel's role in under a minute.
  `runtime_lba_to_offset_seconds()` converts a live-observed physical
  LBA into an approximate elapsed-time offset inside one specific
  channel's own stream, so `activity_window_features()` can compare
  sibling channels' activity at the *exact* confirmed moment --
  much stronger evidence than a whole-clip average.

## A real bug the sanity check caught

Before trusting the classifier on unknown packs, it was run against
`XAPACK08.BIN` -- the one pack with an already-independently-confirmed
answer (`XAPACK08:7`, `KNOWN_CUE_SOURCES[127]`, 100%
reference-decoder-verified, and confirmed by direct listening this
session). **The classifier got it wrong**: it ranked `XAPACK08:4` as
the top DIALOGUE candidate (85%) while the real confirmed dialogue
channel, `XAPACK08:7`, was classified as MUSIC (55%).

Inspecting `XAPACK08:4`'s raw envelope explained why: it has a high
variance (`rms_cv`), which the first version of the classifier treated
as "bursty, speech-plausible" -- but the bursts were **regularly
spaced and near-identical in length** (`[4121, 5413, ..., 13, 13, 13,
13, 13, 391, ...]`, repeating roughly every 10-11 windows), the
signature of a rhythmic loop or repeating SFX, not speech. High
variance alone cannot distinguish a loop from real speech; only
checking whether the *individual burst lengths themselves* are regular
or irregular can. `burst_regularity_cv` (the coefficient of variation
of burst lengths, not amplitudes) was added specifically to catch this,
and a regular-loop channel with high overall `cv` is now correctly
routed to `MUSIC` instead of `DIALOGUE`
(`test_classify_candidate_regression_regular_loop_is_not_dialogue`).

**Re-running after the fix**: `XAPACK08:4` correctly drops to MUSIC
(50%). `XAPACK08:7` (the true dialogue) is *still* not flagged as the
top candidate by the heuristic alone -- its envelope is comparatively
steady (`rms_cv=0.47`, not an outlier among siblings whose values range
~0.4-1.15), because it is one long (~20s), continuously-spoken line
rather than a short, punchy burst-then-silence utterance. This is an
honest, accepted limitation, not something to keep hand-tuning around:
**envelope-shape heuristics are better suited to short clips** (the
1-7 second clips from `XAPACK30`/`32`/`28`/`23` all produced clean,
confident DIALOGUE candidates, 62-85%) **than to long, sustained
single-utterance dialogue**, which needs the runtime-anchor
cross-check or direct listening instead. The runtime-anchor activity
window did help here even where the whole-clip heuristic didn't: at
the real confirmed anchor moment, `XAPACK08:7` showed `1.43x` its own
average activity (well above the `0.008x`-`0.97x` range of the clearly
wrong candidates), even though it wasn't the single highest value
(`XAPACK08:6` showed `1.55x`) -- narrowing the field, not a lone,
perfect answer. Exactly the outcome the four-layer strategy expects:
automation narrows, cross-validation and a human confirm.

## Confirmed so far

- **`XAPACK08:7`** -- `DIALOGUE`, `USER_LISTENING` (+ independently,
  `KNOWN_CUE_SOURCES[127]`'s live LBA anchor and the reference-decoder
  match). The project's first confirmed semantic label, and its
  Golden Audio Asset.

## Real review runs this session

Full review artifacts (WAV + `analysis.json` + `ranking.csv` +
`review.html`) were generated for `XAPACK00`, `XAPACK04`, `XAPACK08`,
`XAPACK23`, `XAPACK28`, `XAPACK30`, `XAPACK32` under
`audio_export/review/<pack>/`. `XAPACK04:6` and `XAPACK04:5` are the
current top candidates for the `XAPACK04` pack specifically (cross-
validated two ways: relative-envelope outlier AND highest runtime-
anchor activity at the moment a live capture confirmed real audio was
playing) -- awaiting direct listening confirmation before being
persisted as confirmed labels.

## What this does NOT do

No ML model, no training pipeline -- per the explicit instruction to
use confirmed examples as training-*by-example* calibration checks
(does the simple heuristic classifier do well against a few known
answers?), not as input to an actual model, at least not yet. No
automatic promotion from `HEURISTIC` to `CONFIRMED` under any
circumstance -- that always requires `save_label()` called with real
`USER_LISTENING` or `RUNTIME_EVIDENCE` provenance, i.e. a human or a
runtime cross-check, never the classifier's own score alone.

## Tests

33 new: `test_audio_semantic.py` (16, including a caught-and-fixed
real edge-case bug: an all-silent clip computed `silence_ratio=0.0`
instead of `1.0` because the 10%-of-mean threshold degenerates to 0
when the mean itself is 0), `test_semantic_label_store.py` (8),
`test_audio_review.py` (9).

## Next step

Listen to the `XAPACK04:6`/`XAPACK04:5` candidates (already exported)
and, if confirmed, persist via `gcrts.semantic_label_store.save_label`
-- growing the confirmed-example set is what will make item 8 of the
original strategy (checking whether a simple classifier already does
well) an answerable question rather than a one-data-point guess.
