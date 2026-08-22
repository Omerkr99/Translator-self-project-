# Live Audio Inspector

The second of the three next-priority items named in the project's own
Fandub Pipeline roadmap. Deliberately adds **no new resolution logic**
of its own — it's a display layer wrapping infrastructure that already
exists and was already proven: `gcrts.runtime_audio.capture_audio_event`
(the live LBA), `gcrts.audio_asset_resolver.resolve_audio_asset` (LBA ->
`AudioAsset`), and `gcrts.dialogue_database` (the unified per-asset
record). `gcrts.live_audio_inspector.inspect_live_audio()` chains the
three together into one `LiveAudioInspection` per poll.

## The one deliberate write

Every other audio module in this project is read-only. This one has
exactly one narrow write: the first time a live LBA resolves to an
`AudioAsset` this project has never seen before, a plain `DETECTED`
entry is registered for it (`build_entry_from_asset` + `save_entry`).
That's the literal, honest meaning of "detected" — not a semantic
guess, since `build_entry_from_asset` only ever reflects an *already*
confirmed label or scaffolded Fandub template, never invents one.

**An asset that already has a database entry is only ever read, never
re-saved.** `build_entry_from_asset` doesn't know about any
`evidence`/`scene_notes`/`notes` a human has added by hand since (those
aren't sourced from the label store or a template) — rebuilding fresh
and overwriting would silently destroy them. `inspect_live_audio()`
checks `get_entry()` first and only calls `build_entry_from_asset` when
that comes back `None`. Regression-tested directly
(`test_inspect_live_audio_never_overwrites_existing_entry`), and
confirmed again in the live smoke test below (`git diff` on the real
database file showed zero changes after 10 polls against an
already-known asset).

## Wiring

`gcrts.runtime_visual_provider.RuntimeVisualProvider` gained
`last_live_audio_inspection`, populated in `scan()` right after
`last_audio_event` (same no-second-fetch pattern as every other audio
field there — reuses the one RAM dump and the one lazily-loaded disc
image already fetched for `_audio_event`). The Visual Inspector's
existing "Audio (live, read-only)" panel now prints a
`format_now_playing()` line first: `NOW PLAYING: <asset_id> [state]
<semantic type> -- <workflow status>` — exactly the text the roadmap
asked for, with `?` appended to the semantic type when it isn't
`USER_LISTENING`/`RUNTIME_EVIDENCE`-confirmed, so an unconfirmed
heuristic guess is never shown as if it were settled fact.

## Live smoke test (this session, PCSX-Redux genuinely running)

```
profile valid: True
NOW PLAYING: XAPACK22:7 [UNKNOWN] DIALOGUE -- TRANSLATION_DRAFT
```

10 consecutive live polls (0.5s apart) against the actually-running
emulator all resolved the same real position to `XAPACK22:7` — the
second confirmed dialogue asset from this session's earlier work — and
correctly pulled its real database entry (`DIALOGUE`,
`TRANSLATION_DRAFT`), unmodified across every poll. `state: UNKNOWN`
here is expected, already-documented behavior, not a bug in this
module: the underlying `0x800A6107` lifecycle byte's PLAYING/STOPPED
transitions are confirmed to not generalize to every real event (see
`gcrts.runtime_audio`'s own module docstring and
`CDROM_SETFILTER_CAPTURE.md`) — this module reports whatever that byte
honestly says, never overrides it.

## Tests

13 new: `test_live_audio_inspector.py` — nothing-to-inspect cases (no
event, no disc bytes, no start LBA), an unresolved LBA still producing
a real reportable result, new-asset auto-registration (and its
`auto_register=False` opt-out), the never-overwrite regression, a
confirmed label being reflected, and `format_now_playing()`'s text for
each case.

## What's next

The third of the roadmap's three named priorities: the Script Pipeline
Investigation (memory-diff between snapshots, or a Ghidra/PCSX-Redux
bridge) — a genuinely different approach from the 5 already-closed
timing-based script-text capture attempts.
