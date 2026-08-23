# Audio Data Trace

The pivot from **control-flow tracing** to **data tracing**, after the
SPU Playback Trace milestone's live Exec-breakpoint approach
(`docs/audio/SPU_PLAYBACK_TRACE.md`) reached diminishing returns this
session.

## Why the pivot

Across many live sessions, the tracer's JSONL output reliably stopped
growing after 2-9 real seconds regardless of what was changed:

- Not the 11 overlay-dependent breakpoints (still happened with
  `SAFE_BASELINE_ONLY = true`, zero breakpoints armed).
- Not the save slot (happened on 6, 7, and 9).
- Not the write frequency (happened at both 60 Hz and 10 Hz).
- Not a mid-recording save-state reload (happened without one).
- Not the executable-identity check added mid-session (happened with
  it fully disabled, `CHECK_EXECUTABLE_IDENTITY = false`).

What *did* stay healthy throughout: `GPU::Vsync` itself, confirmed by
creating a second, disposable listener live in the Lua Console that
kept incrementing a counter long after the real tracer's own listener
had gone silent. That is real, reproducible evidence the instability
is environmental (most likely window-focus-related, consistent with
this project's own long-documented finding that PCSX-Redux auto-pauses
on almost any focus change) or specific to something about the
original listener's own accumulated closure state -- not a logic bug
in this project's control-flow instrumentation, and not something
further breakpoint debugging is likely to fix.

**The new question**: not "which code executes when the line is
heard," but "which bytes in RAM actually change while the line is
heard." A one-shot RAM dump is a fundamentally cheaper, more reliable
operation than a sustained 60 Hz capture loop, and every finding from
today (`CAP0.EXE` identity, the overlay address-range corrections)
remains valid and reusable -- this pivot does not discard that work.

## Pipeline

```
pcsx_lua/dump_ram.lua           -- one-shot 2MB RAM dump, on explicit command only
    dump_ram("run01_before.bin")  -- ~1-2s before the line
    dump_ram("run01_during.bin")  -- during the line
    dump_ram("run01_after.bin")   -- right after
        |
        v
gcrts.audio_data_trace           -- ALL analysis offline, outside the emulator
    diff_regions()                -- cluster changed bytes into contiguous regions
    compute_region_stats()        -- entropy/zero-density/alignment per region
    score_candidate_region()      -- multi-signal ranking, never entropy alone
    classify_audio_likeness()     -- SPU-ADPCM / XA-ADPCM-like / PCM16 heuristics
        |
        v
gcrts.audio_fingerprint           -- match a candidate against the known AudioAsset catalog
    compute_fingerprint()          -- RMS + ZCR per frame, z-score normalized
    match_candidate()              -- sliding cross-correlation, best offset + similarity
```

## Phase 1: minimal, on-demand RAM capture

`pcsx_lua/dump_ram.lua` does almost nothing until called: no vsync
listener, no breakpoints, no continuous loop -- directly applying
today's own lesson that continuous per-frame work inside PCSX-Redux's
Lua environment correlated with instability. Captures the full 2MB
main-RAM window `PCSX.getMemPtr()` exposes (nothing excluded), written
in 64KB chunks to avoid building one giant multi-megabyte Lua string.

**Not yet live-tested** -- built and reasoned carefully (reusing the
same, already-verified `PCSX.getMemPtr()` FFI binding
`gcrts.spu_playback_trace` already uses), but this project's tooling
cannot click through PCSX-Redux's GUI on its own; the first real run
is a human action, same constraint as every other live Lua script this
project has built.

## Phase 2: offline differential analysis

`diff_regions(before, after, min_gap=16)` finds every differing byte
offset and clusters offsets within `min_gap` bytes of each other into
one region -- a real buffer rarely changes every single byte with zero
untouched padding, so requiring strict contiguity would fragment one
real region into dozens of meaningless fragments.

`score_candidate_region()` **deliberately never uses entropy alone**
(compressed non-audio game data is high entropy too) -- it combines:
region size (a real streaming buffer is more than a handful of bytes),
entropy *change* between BEFORE and DURING, absolute DURING entropy,
whether the region changes *again* between DURING and AFTER (a
one-shot, never-reused buffer is weaker evidence than one that's
clearly being rotated/refilled), low zero-byte density, 4-byte
alignment (typical of a real allocated buffer), and -- once multiple
runs exist -- whether the same region reproduces across them
(`mark_stable_across_runs`), which is weighted as strong evidence.
Every contributing reason is recorded alongside the final score, not
just the number.

## Phase 3: audio-likeness heuristics

Three format hypotheses are tested, **never assumed in advance**:

- `spu_adpcm_score`: PS1 SPU ADPCM's real 16-byte block shape (psx-spx)
  -- header byte's filter (0-4) and shift (0-12) nibbles, flag byte
  from the documented value set. Scores the fraction of blocks that
  are plausible.
- `xa_adpcm_like_score`: reuses this project's own already-verified
  128-byte ADPCM group shape (`gcrts.xapack.GROUP_SIZE`/
  `XA_ADPCM_PAYLOAD_SIZE`) for a RAM buffer that might hold XA-ADPCM
  *payload* fragments without their original 2352-byte sector framing.
- `pcm_heuristic_score`: signed-16-bit PCM plausibility via
  sample-to-sample smoothness and nonzero-density -- heuristic only,
  documented as capable of scoring random data moderately too (never
  the sole signal).

## Phase 4: candidate extraction

Only one extraction path is implemented so far --
`extract_candidate_pcm_s16` (raw signed-16-bit mono PCM at 37800 Hz,
the same rate this project's own XA-ADPCM decoder already established
for every real asset on this disc). SPU-ADPCM/XA-like decoding is
intentionally NOT implemented yet -- per this milestone's own
instruction, extraction should follow a real, reproducible candidate
region, not precede it.

## Phase 5/6: fingerprinting and matching (real, validated)

`gcrts.audio_fingerprint` reduces a clip to per-frame `[RMS energy,
zero-crossing rate]`, z-score normalized per clip (so absolute
loudness doesn't matter, only the shape of the energy/ZCR contour --
tolerating gain differences and silence padding). Matching slides the
shorter clip across the longer one, computing a normalized Pearson
correlation at every offset, and reports the best offset and score.
This is deliberately simpler than a perceptual/landmark hash (Shazam-
style) -- documented honestly as a coarse heuristic, not a state-of-
the-art audio fingerprint, chosen because it is the simplest fully
local, dependency-free (numpy only, already a real project dependency)
method that satisfies the actual need: short voice clips, fragment/
offset tolerance, no cloud service.

**Real validation this session** (not synthetic): a genuine 2-second
fragment extracted from the middle of the already-confirmed
`XAPACK08:7` asset, matched against a 2-asset reference database:

```
Rank  AudioAsset            Similarity    Offset (s)
1     XAPACK08:7                 0.945         10.18   (expected ~10.19)
2     XAPACK22:7                 0.660          2.37
```

Correct source, near-exact offset, and a clear separation from the
wrong asset. A known, honestly-documented limitation: this simple
2-feature method can behave unpredictably when a *reference* clip's
own features have near-zero variance (e.g. constant-amplitude noise) --
z-scoring amplifies noise into a spuriously-shaped signal in that
degenerate case. Real speech-like audio (as validated above) does not
exhibit this.

## Phase 7/8: NOT YET STARTED, deliberately

Tracing a candidate region's writer/consumer via new breakpoints is
explicitly gated on having a real, reproducible candidate region first
-- "no new code breakpoint without a data region that justifies it."
No live RAM snapshot has been captured yet this session (Phase 1's
script exists but has not been run), so this remains open.

## CLI

```
python -m gcrts.audio_data_trace diff run01_before.bin run01_during.bin run01_after.bin
python -m gcrts.audio_data_trace analyze-run artifacts/run01/   # expects before.bin/during.bin/after.bin
python -m gcrts.audio_fingerprint build-db [--disc PATH] [--out audio_fingerprints.json]
python -m gcrts.audio_fingerprint match candidate.wav [--db audio_fingerprints.json]
```

All four smoke-tested this session: `diff` against a synthetic
snapshot pair correctly found and scored the one real changed region;
`build-db`/`match` against a real 2-asset subset of the actual disc
correctly identified a real extracted fragment's source asset and
offset (shown above).

## Tests

46 new: `test_audio_data_trace.py` (34 -- diffing/clustering, entropy,
scoring including the explicit "entropy alone is not enough" and
"stability across runs helps" regressions, all three format
heuristics, cross-run correlation) and `test_audio_fingerprint.py` (12
-- PCM normalization, fingerprint round-trips, offset/similarity
matching including a zero-variance-reference regression guard). No
test depends on the real disc image (gitignored, not available in a
clean checkout) -- the real-disc validation above was run manually,
matching this project's own established testing convention.

## What's next

1. Run `pcsx_lua/dump_ram.lua` for real -- capture BEFORE/DURING/AFTER
   around the actual save-slot-9 target line (3+ repeated runs per
   the milestone's own repeatability requirement).
2. `python -m gcrts.audio_data_trace analyze-run` on the result; if a
   plausible audio-like region is found, extract and fingerprint-match
   it against a real, full reference database
   (`python -m gcrts.audio_fingerprint build-db`).
3. Only once a reproducible candidate region exists: Phase 7/8 (trace
   its writer/consumer via new, `CAP0.EXE`-tagged breakpoints, never
   bare addresses -- see `gcrts.overlay_identity`).
4. Any resulting `AudioAsset` match still requires direct human
   listening before `gcrts.semantic_label_store`/`gcrts.dialogue_
   database` ever mark it confirmed -- a fingerprint match is
   `HEURISTIC` evidence, exactly like this project's existing
   automated classifier, never promoted to confirmed on its own.
