# Fandub Replacement Template

Data model and validation-preview rules for the eventual
translator/dub workflow -- **architecture only, no injection**:

```
Dialogue line -> Play Japanese -> Read translation -> Record/import dub
  -> compare duration -> validate -> encode -> replace
```

Only the first five steps exist here. "Encode" and "replace" (actual
re-encoding and disc rebuild) are explicitly out of scope until this
foundation is exercised across many real, confirmed assets.

## Gated on a confirmed semantic label

`gcrts.audio_replacement.scaffold_fandub_project(asset, out_dir)`
refuses (raises `ValueError`) unless the asset already has a
`USER_LISTENING` or `RUNTIME_EVIDENCE` confirmed label in
`gcrts.semantic_label_store` -- a bare `HEURISTIC` candidate guess is
never enough. This prevents a translator-facing project from
accidentally growing around an asset that turns out to be music or
ambience once someone actually listens.

`XAPACK08:7` (the project's first confirmed dialogue asset) already has
a real template scaffolded at `audio_export/fandub/XAPACK08_7/template.json`
(gitignored, same as other `audio_export/` content -- regeneratable
from the real disc image + the committed label store at any time).

## The template (`FandubEntry`)

```
original_asset_id, original_pack_path, original_channel_number,
original_duration_seconds, original_sample_rate_hz, original_channels
  -- pre-filled from the real AudioAsset, never hand-edited

japanese_transcript, translation, speaker, caption_notes
  -- empty until a translator fills them in

replacement_file, replacement_actor, replacement_language,
replacement_duration_seconds, replacement_sample_rate_hz,
replacement_channels
  -- empty until a recording/import exists

validation_status, validation_notes
  -- set by validate_replacement(), see below
```

## Validation is rules-only, never automatic correction

`validate_replacement()` reports facts about a candidate replacement
recording -- it never resamples, re-encodes, or otherwise touches the
audio. Checked in order: format (sample rate + channel count) first,
then clipping (peak amplitude near int16 max), then near-total silence,
then duration difference (>15% of the original flags for review).
Passing all four returns `READY_FOR_ENCODE` -- still just an automated
check, not the same as a human's `APPROVED`.

## Tests

12 new: `test_audio_replacement.py` -- template pre-fill, save/load
round-trip, every validation branch (including that format-mismatch
is checked before duration, so a wrong-format file isn't mis-reported
as merely too long/short), non-mutation of the input entry, and the
confirmed-label gate (including that a bare `HEURISTIC` label is
correctly refused, not just an entirely missing one).
