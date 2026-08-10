# Audio Event Isolation / Extraction

Goal: prove that GCRTS can take one real `RuntimeAudioEvent` and isolate
the exact physical XA sector stream that belongs to it. New module:
`gcrts/audio_event_extraction.py`.

## Headline result

**The extraction backend is built and tested (14 new tests) — but a
live re-check this pass found that the previously-captured Setfilter
call is NOT proven to be event-specific**, which honestly blocks
running the backend against a real, confirmed live event right now.
This is reported directly, not smoothed over: the milestone's own
"Definition of Done" explicitly anticipated this possibility ("If
Setfilter cannot be tied to the chosen event: do not use the historical
Setfilter observation as if it were event-specific") and this is
exactly what happened.

## Phase 1-2: data model audit

| Field | Status |
|---|---|
| `source_file` | LIVE_VERIFIED (`gcrts.runtime_audio`, `gcrts.xa_disc_index`) |
| `source_file_start_lba` | LIVE_VERIFIED (`gcrts.audio_stream_source`, when confidence is `LIVE_VERIFIED`) |
| `source_file_end_lba` | OFFLINE_CONFIRMED (static table, `_LAST_END_LBA`/next-file-start in `gcrts.xa_disc_index`) |
| `runtime_setfilter_file`/`channel` | **PARTIAL** — real, live, reproduced values exist (`file=2, channel=1`), but not proven tied to any specific `RuntimeAudioEvent` (see below) |
| `event_start_lba` | PARTIAL — `AudioStreamSource.file_start_lba` gives a file-level start; a genuine per-*event* start distinct from the file start was not established this pass |
| `event_current_lba` | LIVE_VERIFIED (`gcrts.runtime_audio.RuntimeAudioEvent.position_counter`) |
| `event_end_lba` | **UNKNOWN** — not established this pass either |
| `coding_info`, `submode`, `sector file_number/channel_number` | LIVE_VERIFIED (`gcrts.xa_disc_index.SectorMeta`/`read_sector_meta`) |

Existing extraction-adjacent code found (none duplicated): `gcrts.cdrom.extract_sector_payloads`
(generic, all-sectors de-interleaver — not filter-aware, wrong tool for
isolating one XA channel), `gcrts.xa_disc_index.read_sector_meta` (the
real per-sector metadata reader this module reuses directly).

## Phase 3-5: re-capturing the target event, and the correction it produced

The milestone's own Phase 4 called for verifying whether the historical
`Setfilter(file=2, channel=1)` (from `XA_STREAM_RESOLUTION.md`) was
actually tied to one specific event, rather than assuming it. A new
live capture read the position counter, playback state, and
`last_req_params` at the **exact same instant** as the Setfilter hit —
something the original captures didn't do. Two independent runs (fresh
state reload before each):

```
params = [2, 1]              (unchanged both times)
state = 0x02 (STOPPED)        (never STARTING/PLAYING)
last_req_params = 0x7F (127)  (a stale, already-finished cue's value)
position_counter = 182935     (deep in XAPACK42's range, nowhere near XAPACK02)
```

**Conclusion: this specific Setfilter call is most likely a fixed
default/reset value issued during idle periods, not a per-event channel
selection.** The identical `position_counter` across both independent
captures is itself informative — consistent with a fully deterministic
replay from the same frozen save state, not a value shaped by live
gameplay. This is recorded permanently in `gcrts.cdrom_setfilter` as
`KNOWN_SETFILTER_CONTEXT_CHECKS` and `is_proven_event_specific()`
(returns `False`, with the evidence attached) — not deleted or
softened, per this project's own standing discipline of recording real
corrections rather than quietly moving past them.

A separate attempt to catch multiple Setfilter hits in one longer
session (to see whether the value ever varies) caught only the same
single hit — the emulator settles into an idle state with no further
CD-ROM command activity at all without further player input, matching
a pattern already documented in `XA_STREAM_RESOLUTION.md`'s earlier
blocker writeups.

## Phase 5: event end boundary — still unresolved

No new evidence closed this. The position-polling phase of the capture
found `state` was already `STOPPED` from the very first poll (no
`PLAYING → STOPPED` transition was actually observed in this
session's live window), so no new information about what triggers STOP
was gathered. `AudioStreamSource`'s `+0x08` field remains exactly as
`XA_STREAM_RESOLUTION.md` already described it: observed, static
per-context, plausible "event end" candidate, not independently
confirmed.

## Phase 6-9: the extraction backend (built and tested)

`gcrts.audio_event_extraction` provides:

- `select_event_sectors(disc_bytes, start_lba, end_lba, xa_file_number, xa_channel)`
  — scans a physical LBA range and returns only the LBAs that are real
  CD-XA **audio** sectors (the standard White Book submode Audio flag,
  `0x04`) matching the given file/channel. Correctly excludes the other
  7 interleaved channels and any data/video sectors sharing the same
  range — verified with a synthetic 8-way-interleaved fixture in
  `tests/test_audio_event_extraction.py`.
- `extract_runtime_audio_event(...)` — builds an `ExtractedAudioEvent`
  (selected LBAs, concatenated raw Form2 XA payload, full provenance).
  Returns `ExtractionConfidence.END_UNRESOLVED` immediately (no attempt,
  no fabricated window) when `end_lba` is `None` — never guesses a time
  window, per the milestone's own explicit instruction.
- `extraction_readiness(...)` — pure classification (`NOT_READY` /
  `START_CONFIRMED` / `CHANNEL_CONFIRMED` / `READY`), used by
  `RuntimeSnapshot`/the Visual Inspector to report *why* extraction
  isn't ready rather than a vague boolean.

**Deliberately never defaults `xa_file_number`/`xa_channel`** — a
caller must supply values it has independently confirmed for the
specific event being extracted. This is enforced directly by the
Phase 3-5 correction above: silently defaulting to `(2, 1)` for
whatever event happens to be active would have been exactly the kind
of unproven claim this project's discipline exists to prevent.

## Phase 10-11: output format / decoding

Not reached — extraction was never run against a real, confirmed live
event this pass (no confirmed `xa_file_number`/`xa_channel` for any
specific event, per the correction above). The backend produces raw
concatenated Form2 XA payload bytes (2324 bytes/sector) when given real
inputs; no ADPCM-to-PCM decoder exists in this project and none was
attempted, per Phase 10's own instruction not to let decoding become
the blocker.

## Phase 12-15: structural verification / captions / automatic extraction

Not reached — gated on a real extraction run, which didn't happen this
pass for the reasons above.

## Phase 16: RuntimeSnapshot integration

`RuntimeSnapshot.active_audio[].extraction_status` — one of
`NOT_READY` / `START_CONFIRMED` / `CHANNEL_CONFIRMED` / `READY`,
computed from `extraction_readiness()`. Currently always reports at
most `START_CONFIRMED` for any live event (a confirmed start LBA can
exist via `AudioStreamSource`, but `xa_file_number`/`xa_channel` are
never auto-filled) — an honest, tested ceiling, not a bug (see
`tests/test_runtime_snapshot.py`'s
`test_snapshot_extraction_status_never_defaults_to_ready`).

## Phase 17: Visual Inspector

Added a status line ("Extraction status: ...") using the same
`extraction_readiness()` call. No "Extract Audio Event" action was
added — per the milestone's own instruction not to build UI ahead of a
working backend, and extraction genuinely isn't ready for any live
event yet.

## Phase 18: provenance

`ExtractedAudioEvent.provenance` is a free-form dict a caller can
populate with `ScriptAudioAssociation`/`RuntimeAudioEvent`/Setfilter
identifiers; `to_dict()` includes it. Not populated with real data this
pass since no real extraction ran.

## Phase 19: Setfilter regression coverage

`tests/test_cdrom_setfilter.py` now pins the 3 real command-write call
site addresses found by the earlier static scan
(`0x8008182C`/`0x80081AC8`/`0x80081C2C`) and explicitly asserts none of
them regresses to `0x80081C00` — the address the *original*, buggy
capture used (reading the command byte from the wrong stack offset,
silently returning a plausible-but-wrong `0x00` across three full live
sessions). See `gcrts.cdrom_setfilter`'s module docstring for the full
account of that bug.

## Tests

23 new tests: 14 in `tests/test_audio_event_extraction.py`, 2 in
`tests/test_runtime_snapshot.py`, 6 in `tests/test_cdrom_setfilter.py`
(the "not proven event-specific" correction + regression coverage) + 1
adjustment.

## Live Definition of Done — honestly not met, and why

The milestone's own DoD required a real event to be representable as
`ScriptUnit → selector → XAPACK → Setfilter(file, channel) → start LBA
→ end boundary → matching XA sectors → isolated output`, with the
Setfilter tied to that specific event. This pass's own re-verification
(explicitly required by the milestone's Phase 4) found that link does
not currently hold for the one real Setfilter call this project has
ever caught — it's a fixed value with no proven connection to any
specific event. Per the milestone's own explicit instruction, this is
reported as the real result rather than papered over: **the backend is
proven and tested; running it against one specific, verified live
event is blocked on finding a genuinely per-event Setfilter call (or
another mechanism for determining the true per-event channel), which
this pass did not find.**
