# Subtitle Track Mechanics: Trigger + Per-Cue Duration

The first concrete building block for SDD O5 (external, host-rendered
movie subtitle sync) -- deliberately the simplest piece that could
work: no PS1-side hook, no VRAM write, no disc patching. It reuses
three already-`CONFIRMED_LIVE` pieces (overlay-identity detection, the
external overlay renderer, host wall-clock timing) rather than
building anything new at the reverse-engineering layer.

## The model

A **subtitle track** is one `reference_overlay` (which executable
becoming resident marks the track's own t=0, via
`gcrts.overlay_identity.identify_overlay`) plus an ordered list of
**cues**, each just three numbers and a string:

- `t` -- seconds after the reference overlay becomes resident
- `duration` -- how long this cue stays visible, once shown
- `text` -- what to show

This is `gcrts.overlay_action.SubtitleTrackPayload` (real fields now,
previously a placeholder stub per SRS §8's content model) and
`SubtitleCue`. The runner is `gcrts.subtitle_track_runner.run_subtitle_track`.

## Why this timing model, specifically

`docs/renderer/MOVIE_TIME_SOURCE_INVESTIGATION.md` found host wall-
clock time, anchored at a detected trigger event, byte-for-byte
deterministic through the first ~23 seconds of a boot/movie sequence,
and still mostly accurate after that (17/20 sampled frames matched
exactly across two independent runs). Subtitle cues span multiple
seconds and aren't perceptibly affected by the sub-second drift found
in the later, faster-changing portion of that investigation -- so this
timing source, while not frame-exact, is a real, adequate match for
this specific job. This does **not** require solving
`docs/renderer/VRAM_WRITE_PATH_INVESTIGATION.md`'s still-open blocker
at all -- cues render through the external overlay window, not by
altering VRAM during movie playback.

## Editing a track

A track is a plain JSON file -- editing a subtitle means editing this
file, nothing else:

```json
{
  "track_id": "op_intro",
  "reference_overlay": "MOP.EXE",
  "cues": [
    {"t": 5.0, "duration": 3.0, "text": "..."},
    {"t": 12.5, "duration": 4.0, "text": "..."}
  ]
}
```

`gcrts.subtitle_track_runner.load_subtitle_track(path)` parses this
into a `SubtitleTrackPayload`. The on-disk shape is deliberately
friendlier than `SubtitleTrackPayload.to_dict()`'s own machine-facing
format (short key names, no `"kind"` wrapper) -- authoring a track
should never require touching Python. `subtitle_tracks/op_intro.example.json`
is a real example (placeholder text, real structure) against the one
movie already `CONFIRMED_LIVE` for detection
(`MOP.EXE`/`OP.STR`, per `docs/renderer/MOVIE_DETECTION.md`).

## Running a track live

```
python -m scripts.run_subtitle_track subtitle_tracks/op_intro.example.json
```

Waits for `reference_overlay` to become resident (GDB polling, same
mechanism as `scripts/live_overlay_watch.py`), then shows each cue in
chronological order (sorted by `t`, regardless of file order) through
`gcrts.external_overlay_renderer.ExternalOverlayRenderer` -- the same
renderer Stages 2-3 already proved live. `--out` writes a JSON record
of when each cue actually fired (`CueResult.shown_at_t`, elapsed time
since the reference trigger) for comparison against the intended `t`.

## Live confirmation

Run live against a real PCSX-Redux instance (fresh boot via
`PCSX.hardResetEmulator()`+`PCSX.resumeEmulator()`, per
`docs/tooling/PCSX_REDUX_CAPTURE_PROTOCOL.md` section 18): both cues
in `op_intro.example.json` fired within a few hundred milliseconds of
their intended offsets (`t=5.0s` → shown at `t=5.249s`; `t=12.5s` →
shown at `t=12.726s`), and a real desktop screenshot (not `PrintWindow`
on a single window, which wouldn't show a separate overlapping Tk
window -- a full composited desktop capture instead) caught the
overlay text rendering directly over real game content (the HUMAN
ENTERTAINMENT publisher-logo scene), confirmed in two consecutive
captures ~1.5s apart. Evidence:
`evidence/subtitle_track_live_proof/` (`cue1_overlay_visible.png`,
`before_cue_no_overlay.png`, `run_results.json`, `record.json`). This
closes the "no live end-to-end run" gap below.

## Real audio-derived timing for OP.STR

`subtitle_tracks/op_intro.json` (distinct from
`op_intro.example.json`, which stays as the minimal illustrative
example) now has **real cue timing derived from OP.STR's actual
audio**, not fabricated or guessed: `gcrts.movie_str_audio` extracts
the movie's exact raw bytes from the real disc image and demuxes its
audio track via FFmpeg's `psxstr` support (confirmed live to
auto-detect this exact file: `Video: mdec 320x240 15fps`,
`Audio: adpcm_xa 37800Hz stereo`); `gcrts.audio_activity_segments`
finds amplitude-based activity segments; `scripts/build_op_intro_track_from_audio.py`
converts them into real `SubtitleCue` entries with the text left as an
explicit `TBD` placeholder. Live-run result: **14 cues, all firing
within ~0.2-0.9s of their real audio-derived offsets** against a fresh
boot (`evidence/op_intro_audio_derived_track/`).

**Honest scope of what this timing actually is**: amplitude-based
activity detection, not speech detection. It found 15 total segments;
14 short ones (0.5-5.7s, plausibly one line each) from t≈11s to t≈48s,
then one long ~80s block from t≈72s onward that's almost certainly
continuous background music (a movie's theme song, say) rather than
discrete dialogue -- deliberately excluded from the generated track
rather than included as one absurd 80-second "cue." **The text for
every cue is still `TBD`** -- someone needs to listen to
`op_audio_extracted.wav` (or re-watch `OP.STR` with sound) to confirm
which segments are real dialogue, correct exact boundaries by ear, and
write the actual translated lines. The mechanism and the timing
pipeline are both now real; the content is the one piece left that
requires a human who can actually hear the audio.

## What this does NOT do yet

- **Single reference overlay per track.** A track can't currently span
  multiple executables (e.g. a cutscene that transitions between two
  movie-player residencies) -- out of scope until a real need for it
  appears.
- **Not frame-exact.** Per the timing investigation above, this is
  appropriate for cues spanning multiple seconds, not for anything
  requiring sub-second precision.
