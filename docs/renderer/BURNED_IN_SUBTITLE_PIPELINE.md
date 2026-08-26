# Burned-In Subtitles: CONFIRMED_LIVE End-to-End

**Supersedes the framing (not the code) of `docs/renderer/SUBTITLE_TRACK_MECHANICS.md`
for movies specifically.** Direct user correction (2026-08-26, recorded
in the `project-fandub-goal` memory): the actual goal is a translation
patch that survives being burned to a real CD and played on real PS1
hardware, "כמו שאר הfan translations שיש היום" (like other fan
translations that exist today). A burned disc has no host machine
running Python code next to it — so `gcrts.subtitle_track_runner` +
`ExternalOverlayRenderer` (this same session's own subtitle-track work,
live-proven in `evidence/subtitle_track_live_proof/`) is a genuinely
useful **tool for proving cue timing and rehearsing content against an
emulator**, but it is not itself shippable. The deliverable mechanism
for movies has to be **offline and disc-resident**: subtitle text
burned directly into the movie's own video frames, patched into a copy
of the disc image — the same shape of solution Stage 4 already proved
for regular dialogue text (static disc patch, verified to survive a
real cold boot), applied to video instead of script bytes.

**As of the same session, this entire pipeline is `CONFIRMED_LIVE`**:
a real subtitle, burned into real `OP.STR` video frames, re-encoded to
a genuine PS1 MDEC/STR bitstream, patched into a disc image copy,
played back correctly and visibly on a real running emulator. See
`evidence/burned_in_subtitle_live_playback/` for the full proof.

## The encoder gap is closed: `psxavenc`

FFmpeg's own `mdec` support is decode-only, but a real, actively-
maintained, third-party PS1 A/V encoder exists and works:
[`psxavenc`](https://github.com/WonderfulToolchain/psxavenc)
(prebuilt Windows binary at
`https://github.com/WonderfulToolchain/psxavenc/releases/download/v0.3.1/psxavenc-windows.zip`).
Its defaults matched this game's own real `OP.STR` stream properties
exactly (`320x240`, `15fps`, `37800Hz` stereo XA-ADPCM) — no parameter
tuning was needed. `gcrts.movie_str_encoder.encode_str` wraps it.

## The full pipeline, confirmed step by step

1. **Decode.** `gcrts.movie_str_audio` reads `OP.STR`'s real raw bytes
   from the disc and demuxes it (already proven for audio extraction;
   the same path also yields video frames via FFmpeg's `psxstr`).
2. **Plain round-trip test, no edits** — done first, per this
   project's "prove the mechanism before using it for the real thing"
   discipline: re-encoded the *unmodified* decoded video via
   `psxavenc`, patched it into a disc image copy at `OP.STR`'s real LBA
   (`gcrts.disc_text_patch.build_patched_disc_copy`, the same primitive
   Stage 4 already proved for script text), booted it live — confirmed
   clean, correct playback, visually matching the original.
3. **Edit.** `gcrts.burn_in_subtitle.burn_subtitle_onto_frame` burned
   `"-insert text here-"` onto exactly the frames within one ~2-second
   cue window — verified directly (not assumed) that the frame just
   outside the window has no text and the boundary frames do.
4. **Re-encode with edits**, then independently re-verify (by
   re-decoding the *output* `.str` file itself, not the intermediate)
   that the burned text survives the encode at the exact intended
   frame numbers — confirming `psxavenc` preserves pixel edits
   correctly through its own compression.
5. **Patch and verify bytes.** Confirmed the disc-patched copy's bytes
   at the target physical offset are byte-identical to the encoded
   `.str` file — the patch step itself introduces no corruption.
6. **Boot and visually confirm.** Booted the patched disc live and
   located the real on-screen appearance time (see the calibration
   note below), capturing two independent screenshots both clearly
   showing the burned-in text rendering correctly over real movie
   footage.

## A real, load-bearing timing-calibration finding

The naive assumption "movie frame `n` at 15fps appears at
`t_ref + n/15` seconds, where `t_ref` is the moment
`gcrts.overlay_identity` detects `MOP.EXE` resident" was **wrong** for
a freshly-patched disc image specifically: the intended window
(`t_ref+10.85s` to `t_ref+12.85s`, based on the original file's own
timing) actually appeared at `t_ref+21.5s` to `t_ref+23.3s` — a
consistent ~10.7s offset, discovered by scanning a wide real-time
window and locating the text empirically rather than trusting the
frame-count math. Plausibly a one-time CD-ROM seek/buffer-priming
delay specific to a disc location being read for the first time in a
given process's lifetime; not yet root-caused further. **Anyone
reusing frame-count-based timing against a freshly-loaded disc image
should verify empirically first**, exactly as this session did, rather
than trusting the arithmetic alone.

## Consolidated into a reusable tool

The manual, scratchpad steps above (decode, edit one specific frame
range, remux, encode, patch -- run by hand this session to prove the
mechanism) are now `gcrts.movie_subtitle_burner`: `cue_to_frame_range`
and `burn_cues_onto_frame_files` (pure, unit-tested — given a whole
`SubtitleTrackPayload`, not just one cue, they compute each cue's own
frame range and burn all of them onto the right frames, verified
against exactly the live-confirmed window above) plus
`build_burned_in_movie`/`patch_movie_into_disc` (the live orchestration
wrapping FFmpeg + `psxavenc` + disc I/O, manually verified only, same
convention as every other live/external-tool module in this project).
This is what turns "one cue burned in by hand" into "burn an entire
real subtitle track into a movie" as a single reusable call, rather
than repeating this session's manual steps for every cue.

## What remains

- **Real hardware verification** (burn to an actual CD, test on real
  PS1 or a verified-accurate alternate emulator) — not attempted this
  session. Nothing in the pipeline is emulator-specific, but this is
  still an unverified claim, not a confirmed one, until tried.
- **The full `subtitle_tracks/op_intro.json` track** (14 real,
  audio-derived cues) has only been proven for one placeholder cue —
  burning in and verifying the complete set is real remaining work,
  not just repetition (each cue needs its own frame range located and
  the timing-calibration offset re-confirmed).
- **Real translated text.** Every cue so far uses illustrative or `TBD`
  placeholder text — someone who can hear the actual dialogue still
  needs to write the real lines.
- `psxavenc`'s own encoding parameters (quality/bitrate, BS v2 vs v3)
  were used at defaults, never tuned or compared against alternatives.

## What does NOT need to wait for any of this

- `gcrts.audio_activity_segments` (real, audio-derived cue timing) is
  unaffected by any of the above — the *timing* doesn't depend on
  which rendering mechanism ultimately ships.
- `gcrts.subtitle_track_runner` remains valuable for quickly rehearsing
  translated text against a live emulator during authoring, even now
  that a burned-in pipeline exists — it's a faster iteration loop than
  a full decode/edit/encode/patch/reboot cycle for trying out wording
  and rough timing before committing to a real burned-in pass.
