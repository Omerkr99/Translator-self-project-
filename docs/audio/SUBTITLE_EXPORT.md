# Subtitle Export

The first real "product access" deliverable scoped deliberately to
**text-only subtitles** — no audio recording, no injection, per the
project's own prioritized order (subtitles before dubbing). Requested
directly: give the confirmed save-slot-9 voice line
(`XAPACK22:7`) a subtitle-level translation first.

`gcrts.subtitle_export` builds a standard `.srt` file from a
`DialogueDatabaseEntry`'s already-real translation, timed against the
asset's own real, physically-derived `duration_seconds` — never a
guessed or rounded number.

## What it refuses to do

`build_subtitle_cue()` raises `ValueError` on an entry with no
translation yet — this module never invents subtitle text. It also
never silently upgrades confidence: `subtitle_caveat()` reports
`transcript_verified`/`translation_approved` honestly in a JSON sidecar
(`<file>.srt.meta.json`), so a still-unverified draft subtitle is never
indistinguishable downstream from an approved one.

## A real data bug caught and fixed during this pass

The first export produced a duplicated speaker line:
`"ユカリ (Yukari): Yukari: ....Oh, right."` — because the stored
`translation` field already had the speaker prefix baked in from an
earlier session (`"Yukari: ....Oh, right."`), on top of the separate
`character` field the subtitle cue also prefixes. Fixed at the source,
not papered over in the formatter: normalized `character` to `"Yukari"`
and `translation` to just `"....Oh, right."` in both the Fandub
template (`audio_export/fandub/XAPACK22_7/template.json`) and the
Dialogue Database entry, with an honest note recorded on the entry
(`notes` field) documenting the cleanup. Re-exporting produced the
correct single line: `"Yukari: ....Oh, right."`.

## Real output (this session)

`audio_export/fandub/XAPACK22_7/subtitle.srt`:

```
1
00:00:00,000 --> 00:00:05,387
Yukari: ....Oh, right.
```

Sidecar `audio_export/fandub/XAPACK22_7/subtitle.srt.meta.json` carries
the real, honest caveat: the Japanese transcript is not yet
human-verified as belonging to this exact audio moment (it was
screenshot-captured from the screen immediately preceding the confirmed
audio, per the Fandub template's own `caption_notes`), and the
translation is a draft, not yet approved. Both `.srt` and its
`.meta.json`, along with both Fandub `template.json` files, are
force-added past `.gitignore`'s `audio_export/` rule — same precedent
as `semantic_labels.json`/`dialogue_database.json`: real, hand-authored
translation text, not audio.

## Tests

15 new: `test_subtitle_export.py` — timestamp formatting (including
hour rollover and millisecond rounding), cue construction (real
duration, start offset, missing-translation refusal), `.srt` block
formatting with/without a speaker, file round-trip, the caveat text for
every verified/approved combination, and the `asset_id -> file`
convenience wrapper (including its `KeyError` for an unknown asset).

## What's next

Human review: the draft translation ("....Oh, right.") and the
transcript's exact line-ownership both still need the user's own
confirmation before `transcript_verified`/`translation_approved` can
honestly flip to `True` and the workflow status can advance past
`TRANSLATION_DRAFT`. Separately, the third of the roadmap's three named
priorities remains open: the Script Pipeline Investigation
(memory-diff between snapshots, or a Ghidra/PCSX-Redux bridge).
