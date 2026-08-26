# Burned-In Subtitles: The Real Deliverable Path for Movies

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

## What's confirmed so far

**The pixel-editing half works.** `gcrts.burn_in_subtitle.burn_subtitle_onto_frame`
draws subtitle-style text (white, black outline, bottom-centered) onto
a real frame decoded from `OP.STR` via FFmpeg's `psxstr`/`mdec` support
(the same decode path `gcrts.movie_str_audio` already uses for audio
extraction). Confirmed live: `evidence/burned_in_subtitle_concept/`
shows `"-insert text here-"` burned cleanly into a real decoded frame,
correctly positioned, not corrupting the rest of the image.

## What's still completely unbuilt: the encoder

FFmpeg's own `mdec` support is **decode-only** — there is no
PS1-compatible MDEC *encoder* in stock FFmpeg, so an edited frame
sequence cannot currently be turned back into bytes the PS1's own
movie player will accept. This is the real, hard, unproven step:

1. Decode `OP.STR` to individual frames (done, confirmed).
2. Edit frames (burn in text) (done, confirmed, for a single still frame).
3. **Re-encode the frame sequence back into a valid PS1 STR/MDEC
   bitstream** (NOT done, NOT proven possible with current tooling).
4. Patch the re-encoded `.STR` bytes into a copy of the disc image
   (mechanically similar to `gcrts.disc_text_patch`'s already-proven
   approach for script text, but has not been attempted for video
   data specifically — video files are far larger and the byte layout
   is a full bitstream, not a fixed-width record).
5. Verify the patched copy plays back correctly (visually, and ideally
   audio-synced) on a real emulator, then eventually real hardware.

Step 3 is where this stops today. Community PS1 homebrew tooling for
STR/MDEC encoding exists in principle (e.g. `psxavenc` is a
commonly-referenced open-source encoder) but **has not been evaluated,
installed, or tested in this project as of 2026-08-26** — that
evaluation is real, separate work, not yet started.

## Recommended next step, if pursued

Before attempting anything with burned-in text, prove the encoder in
isolation first, matching this project's own standing discipline
(the same "prove it before using it for the real thing" approach
applied to VRAM-write-path and movie-time-source):

1. Find and install a real PS1-compatible STR/MDEC encoder.
2. **Plain round-trip test, no edits at all**: decode `OP.STR` to
   frames + audio, re-encode with ZERO changes, patch into a disc copy,
   and confirm it plays back correctly (visually and audibly) in the
   emulator — before ever attempting to add subtitle text. If a
   bit-for-bit clean round-trip doesn't work, burning in text won't
   either, and that's the actual blocker to solve first.
3. Only then: re-encode WITH `gcrts.burn_in_subtitle` applied to each
   frame during the window a real cue should be visible, and repeat
   the disc-patch-and-verify cycle.

## What does NOT need to wait for this

- `gcrts.audio_activity_segments` (real, audio-derived cue timing) and
  the eventual real translated text for each cue are still useful and
  reusable once step 3 above is solvable — the *timing* doesn't depend
  on which rendering mechanism ultimately ships.
- `gcrts.subtitle_track_runner` remains valuable for quickly rehearsing
  translated text against a live emulator during authoring, even after
  a burned-in pipeline exists — it's just not the final product.
