# Dialogue Asset Database

Phase 1 of the "Fandub Management Layer" roadmap: turns the research
already done (source identity, physical format, semantic
classification, human-confirmed labels, Fandub templates) into one
real, queryable system instead of scattered files. This is the
foundation everything else (Audio Asset Explorer UI, Live Audio
Inspector, Translation Dashboard) reads from.

## What it combines

`gcrts.dialogue_database.build_entry_from_asset(asset)` reads from
three already-existing, separate stores and merges them into one
`DialogueDatabaseEntry`:

- `gcrts.xapack.AudioAsset` -- physical identity (pack, channel,
  duration, sample rate, channels).
- `gcrts.semantic_label_store` -- the confirmed (or unconfirmed)
  semantic label, if any. `semantic_confirmed` is only `True` for
  `USER_LISTENING`/`RUNTIME_EVIDENCE` -- a bare `HEURISTIC` guess never
  counts, matching every other layer's discipline in this project.
- `gcrts.audio_replacement.FandubEntry` (if a template has been
  scaffolded for this asset) -- character, transcript, translation.

## Workflow status is derived, never asserted

`compute_workflow_status()` looks at what fields are ACTUALLY present
and derives the furthest-along status consistent with that:

```
DETECTED -> TRANSCRIPT_ADDED -> TRANSCRIPT_VERIFIED -> TRANSLATION_DRAFT
  -> TRANSLATION_APPROVED -> READY_FOR_RECORDING -> RECORDED
  -> AUDIO_VALIDATED -> READY_FOR_INJECTION
```

A translation existing but not `translation_approved` stays at
`TRANSLATION_DRAFT`, never jumps to `APPROVED`. `RECORDED`/
`AUDIO_VALIDATED`/`READY_FOR_INJECTION` are external actions this
module has no way to perform or infer -- once set (by a future
recording tool), recomputing status never silently regresses past
them.

## Evidence is additive, real, never fabricated

`evidence` is a plain list of short factual strings a caller appends
via `add_evidence()` -- nothing in this module invents evidence text.
The two real entries populated this session carry the actual
investigation history:

- **`XAPACK08:7`**: `KNOWN_CUE_SOURCES[127]` live LBA match, 100.0000%
  reference-decoder verification, direct user listening confirmation.
- **`XAPACK22:7`**: four independent live LBA captures (including
  appearing at `t=0.0s`, the strongest timing evidence), direct user
  listening confirmation, a real on-screen transcript (not yet
  confirmed to belong to this exact line vs. the preceding screen),
  and the closed dead end of 5 failed automated script-text captures.

## Current real state

```python
from gcrts.dialogue_database import dashboard_summary
dashboard_summary()
# {"total_assets": 2, "confirmed_semantic_labels": 2,
#  "by_status": {"DETECTED": 1, "TRANSLATION_DRAFT": 1},
#  "by_semantic_type": {"DIALOGUE": 2}}
```

`XAPACK08:7` sits at `DETECTED` (no Fandub template transcript/
translation has been filled in for it yet -- only `XAPACK22:7` has).
`XAPACK22:7` sits at `TRANSLATION_DRAFT` (transcript + draft
translation present, neither transcript-verified nor
translation-approved yet).

## Tests

22 new: `test_dialogue_database.py` -- every workflow-status transition
(including the "never regress past RECORDED" guard), confirmed-vs-
heuristic label handling, Fandub template field pull-through, evidence
accumulation (including the missing-entry `KeyError`), and query/
dashboard helpers.

## What's next (per the project's own prioritized roadmap)

1. Expand the confirmed-example set (more `DIALOGUE`/`MUSIC`/
   `AMBIENCE`/`SFX` assets) so the semantic classifier's calibration
   checks become meaningful with more than 2 data points.
2. A Live Audio Inspector (GUI on top of the already-working LBA
   resolver) -- shows `NOW PLAYING: <asset_id>` with its database entry
   in real time during gameplay.
3. Script Pipeline Investigation via memory-diff/breakpoint tracing
   (or a Ghidra/PCSX-Redux bridge) -- a genuinely different approach
   from the 5 already-closed timing-based capture attempts.
