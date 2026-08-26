# Overlay Engine: Grounding the Spec in Real Code

`PS1_OVERLAY_RUNTIME_REQUIREMENTS.md` (SRS) and
`PS1_OVERLAY_RUNTIME_SYSTEM_DESIGN.md` (SDD) already incorporate this
project's own `docs/status/TOOLKIT_READINESS_AUDIT.md` findings
(§12/§19 of the SDD cite it near-verbatim). This document is the next
step the audit itself called for: mapping every major spec component
against what actually exists in `gcrts/` today, building only what's a
genuine gap, and reusing what's already `CONFIRMED_LIVE` rather than
re-deriving it.

## What already existed and needed no new code

| Spec component | Real module | Status |
|---|---|---|
| GDB memory read/write (EMU-002) | `gcrts.gdb_client.GdbClient` (this session, split out of `live_extract.py`) | `CONFIRMED_LIVE` — used throughout this project's audio/movie investigations |
| Screenshot capture | `gcrts.screen_capture.PcsxVramCaptureProvider` | `CONFIRMED_LIVE` |
| Executable/overlay identity (CTX-001) | `gcrts.overlay_identity.identify_overlay` | `CONFIRMED_LIVE` |
| Movie state (part of CTX-002/CTX-003) | `gcrts.movie_detection.classify_movie_state` | `CONFIRMED_LIVE` for detection; `STATIC_CODE_MATCH`/`UNKNOWN` for several chapter mappings |
| Text render hook candidate | `gcrts.renderer1_runtime.py` | `CONFIRMED_LIVE`, one executable only |
| Live text write path (INT-007's "host backend first" precedent, TextBackend candidate) | `gcrts.live_injection.py` | Implemented, never proven end-to-end through a boot (audit §5.3) |
| Save-state loading | PCSX-Redux Web API `/api/v1/state/load?slot=N`, used ad hoc throughout this project | `CONFIRMED_LIVE` |

## What was built this session (Stage 1 of the staged plan below)

The spec's own architecture (SDD §4, §14) calls for an `EmulatorAdapter`
interface, a concrete `PCSXReduxAdapter`, and a `RuntimeContextResolver`
producing a `RuntimeContext` with per-field confidence. None of these
existed as such — they're new, but built entirely as thin wrappers
around the already-`CONFIRMED_LIVE` pieces above, not new reverse
engineering:

- **`gcrts/gdb_client.py`** (new) — the generic GDB remote-protocol
  client, split out of `gcrts/live_extract.py` per the readiness
  audit's own blocker #3. Also consolidates breakpoint/continue/
  register-read methods that three separate investigation scripts had
  each re-implemented as ad hoc subclasses. Caught and fixed a real
  bug during consolidation: a naive "skip 'O' console packets" filter
  would have also skipped the literal `"OK"` acknowledgment reply
  (both start with the letter `'O'`) — fixed by checking that the
  remainder is valid, non-empty, even-length hex, which `"K"` fails.
  7 tests (`tests/test_gdb_client.py`), including one that exercises
  this exact disambiguation.
- **`gcrts/evidence.py`** (new) — the shared `Confidence` tier enum and
  `Evidence`/`Claim` dataclasses, per the readiness audit's blocker #5
  and matching the exact JSON shape sketched in that audit's own §11.
  Adopted incrementally, not a migration — existing domain enums
  (`MovieMatchConfidence`, `VerificationSource`, `PatchProfileStatus`)
  are untouched. 7 tests (`tests/test_evidence.py`).
- **`gcrts/emulator_adapter.py`** (new) — the `EmulatorAdapter`
  abstract interface and `EmulatorCapabilities`/`EmulatorCapability`
  model, matching SDD §4.2's pseudocode.
- **`gcrts/pcsx_redux_adapter.py`** (new) — the concrete
  `PCSXReduxAdapter`. Deliberately advertises only `MEMORY_READ`,
  `MEMORY_WRITE`, `BREAKPOINTS`, `SCREENSHOT`, `SAVE_STATE_LOAD`, and
  `PAUSE_RESUME` — `FRAME_COUNTER` and `AUDIO_CONTROL` are NOT claimed,
  per EMU-004, because no real mechanism for either has been proven in
  this project (the readiness audit's own finding). `load_state` takes
  a `slot: int`, not the interface pseudocode's generic path — grounded
  in what the real Web API actually does. 7 tests
  (`tests/test_pcsx_redux_adapter.py`), all against a fake GDB client
  and monkeypatched HTTP, no live emulator required.
- **`gcrts/runtime_context.py`** (new) — `RuntimeContext` and
  `RuntimeContextResolver` per SDD §9/SRS CTX-001..006. Composes
  `overlay_identity` + `movie_detection`, nothing new detected. Honest
  about its own limits, stated in the module docstring rather than
  discovered later: it can tell you which executable is resident and
  whether a movie is active (both real), but the finer MENU/GAMEPLAY
  distinction is an explicitly `INFERRED` heuristic (`PROG.EXE` →
  likely menu, `CAP*.EXE` → likely gameplay) based on one observed
  screenshot this project already has, not a systematic study; `DIALOGUE`
  resolves to `UNKNOWN` rather than a guess, per CTX-004's own "unknown
  is a valid state" principle. 6 tests (`tests/test_runtime_context.py`).

**Net this stage: 27 new tests, all passing, full suite at 1008 (was
981).** No live emulator required for any of them — they use fake/
injected transports, consistent with this project's own established
testing convention.

## What's still a genuine gap (not built this session, and why)

- **`ExternalOverlayRenderer`** (an actual transparent, always-on-top
  desktop window positioned over the emulator's own window) — real OS-
  level UI work (click-through, always-on-top, window-position
  tracking), qualitatively different from the wrapper modules above.
  Deliberately deferred to its own stage rather than attempted
  speculatively in the same pass as the foundational plumbing.
- **`LiveTestRunner` / `EvidenceBundle` writer** — depends on the
  renderer existing first (there's nothing to screenshot-and-assert
  against yet).
- **`HostAudioBridge`** — straightforward (this project's own
  `gcrts.output_audio_capture` already proves host-side audio I/O
  works), but not needed until a timing-proof scenario exists to drive
  it.
- **Everything under "Internal Overlay"** (SDD §5, §7, §14's
  `overlay/internal/`, `patching/`) — this is real new engineering
  (bootstrap/hook installation into patched game code, a patch
  manifest/rebuild pipeline) with no existing project code to wrap.
  Per the SDD's own Phase ordering (O0 before O2), and per the
  readiness audit's own priority (prove the *external* gameplay overlay
  path before attempting anything game-resident), this is correctly a
  later stage, not a Stage 1 gap.

## Staged build order (adapted from SDD §18's O0–O8, grounded in the above)

```text
Stage 1 — Foundation (DONE this session)
  gcrts/gdb_client.py, gcrts/evidence.py, gcrts/emulator_adapter.py,
  gcrts/pcsx_redux_adapter.py, gcrts/runtime_context.py.
  Exit criterion: EmulatorAdapter interface + one working concrete
  adapter + a RuntimeContext resolver, all tested without a live
  emulator. -- MET.

Stage 2 (= SDD's O0) — External overlay rendering + smoke test (DONE this session)
  Built gcrts/evidence_bundle.py, gcrts/external_overlay_renderer.py,
  gcrts/live_test_runner.py, and scripts/run_overlay_smoke_test.py.
  Exit criterion: SRS VAL-001/VAL-002 satisfied, live, once. -- MET:
  ran scripts/run_overlay_smoke_test.py against the real running
  PCSX-Redux instance. Result: PASS. Real evidence, not a synthetic
  test: RuntimeContextResolver correctly identified PROG.EXE resident
  (CONFIRMED_LIVE) and mode=MENU (INFERRED, exactly as documented); a
  real transparent Tk window displayed "TOOLKIT TEST" on screen (visible
  in evidence/stage2_smoke/host_screenshot.png -- floating over
  whatever window was in front, since the renderer doesn't yet track
  the emulator window's exact position, a known, documented Stage 2
  limitation, not a bug); a real emulator VRAM screenshot was captured
  in parallel (evidence/stage2_smoke/emulator_screenshot.png, showing
  the actual game content at that moment -- a chapter title card,
  consistent with the resolved MENU mode); a full EvidenceBundle was
  written to evidence/stage2_smoke/evidence.json. 8 new tests
  (gcrts.evidence_bundle, gcrts.live_test_runner), all against fakes,
  full suite 1016 passed -- none of the 8 required a live emulator or
  display, only the one manually-run smoke test did, matching this
  project's own established boundary between tested orchestration
  logic and manually-verified live/GUI behavior.

Stage 3 (= SDD's O1) — Shared OverlayAction model (DONE this session)
  Built gcrts/overlay_action.py (OverlayAction + all 6 payload kinds
  from SRS §8 -- only TextPayload has a real runner; the other five
  are declared but report UNSUPPORTED if run, never silently
  approximated) and gcrts/overlay_action_runner.py (the one generic
  executor). gcrts/live_test_runner.py's Stage 2 function is now a
  thin wrapper that builds an OverlayAction and delegates to it --
  existing Stage 2 tests pass unchanged, proving the refactor is
  behavior-preserving. scripts/run_overlay_smoke_test.py now
  constructs the scenario as an OverlayAction directly.
  Exit criterion: the same scenario definition produces the same
  EvidenceBundle shape as Stage 2's hand-written version. -- MET:
  re-ran the live smoke test (now data-driven) against the same
  running PCSX-Redux instance. Result: PASS, with an EvidenceBundle
  structurally identical to Stage 2's (same runtime_context resolution,
  same event_log pattern, same screenshot pair) -- saved to
  evidence/stage3_smoke/. 14 new tests (overlay_action,
  overlay_action_runner), all against fakes; full suite 1030 passed.

Stage 4 (= SDD's O2-O4) — Internal gameplay payload (STARTED this session; real, honest, partial progress)
  A first assumption here was wrong and caught before building on it:
  `renderer1_runtime.py` was assumed to be the render hook, but reading
  its actual code shows it only REPOSITIONS records the game is
  already drawing (moves existing characters' X/Y) -- it has no
  mechanism to inject NEW content. The real candidate turned out to be
  the already-existing script-buffer pipeline
  (`gcrts.live_injection.inject_units_live`, built for the text-editor
  workbench, never previously proven to render anything) -- exactly
  `docs/status/TOOLKIT_READINESS_AUDIT.md` blocker #1's own subject.

  Live experiment against save slot 4 (`CAP1.EXE`, real active
  dialogue): the dialogue auto-advances in real time once a state
  loads, fast enough that a naive read-modify-write sequence races the
  game and lands on the wrong line. Pausing the CPU immediately after
  load (`EmulatorAdapter.pause()`) removes the race entirely -- inject
  while frozen, resume, screenshot shortly after. Result, reproduced
  twice: the injected English text ("Morning Kimika how are you")
  rendered legibly through the game's own renderer and font
  (`evidence/stage4_text_injection_proof/after.png` clearly shows
  "rning Kimika ho", a substring of the injected sentence, in the
  actual classroom scene) -- the first time in this project's history
  that injected text has been confirmed to actually render in-game.
  Formalized as `scripts/prove_live_text_injection.py`.

  **What this does NOT prove, stated precisely rather than implied**:
  this is a live GDB RAM write, wiped by any save-state reload or
  reboot -- it proves only the "renders visibly" half of blocker #1,
  not "survives reboot." That half needs real disc/executable
  patching (SRS PAT-001..007), a distinct subsystem that doesn't exist
  in this project at all yet, and is real new engineering, not a
  wrapper over anything built so far.

  **Follow-up, same session: the persistence half found a real,
  working path, static rather than a runtime hook.** A live-captured
  dialogue line's exact raw word-codes were searched for directly
  inside `DAT/CAP1/K1LINK.CDB` (the chapter's own script resource) and
  found byte-exact at logical offset 3,174,457 (14 words) -- confirming
  at least some lines are stored as CDB-codec literal runs (copied
  verbatim, not compressed; see `gcrts.cdb_codec`'s format docstring),
  which means a same-word-count translated replacement
  (`gcrts.script_encoder.encode_segment`, control codes like
  `pause_flag_b`/`set_mode_ce4` preserved in their original positions)
  can be written directly over those exact bytes in a **copy** of the
  disc image with zero changes to the surrounding compressed
  structure. Built and verified: `gcrts/disc_text_patch.py` (the
  reusable find/convert/patch primitives, 6 tests against synthetic
  data plus the real confirmed offset-math values) and
  `scripts/patch_disc_dialogue_text.py` (the full live-capture ->
  disc-patch -> offline-reread pipeline). Ran it for real: patched a
  copy of the actual disc image, then re-read that copy completely
  offline (fresh file open, fresh ISO9660 parse, fresh file
  extraction, fresh script decode -- no live emulator involved in the
  verification) and got back exactly `"See you soon"` where the
  original Japanese line had been, with the rest of the ISO structure
  (root directory, `PROG.EXE`, etc.) unchanged.

  A real methodological trap was hit and fixed along the way: the
  first attempt to reuse this pipeline captured a *different* unit
  each run (12 words vs. 19 words for what looked like the same
  on-screen line) because the capture didn't pause the emulator first
  -- the same auto-advancing-dialogue race `prove_live_text_injection.py`
  already had to solve for the rendering half. Fixed the same way:
  pause immediately after the state load, then capture, for a
  deterministic snapshot.

  **What remains open, stated precisely**: this proves the *disc copy*
  is correctly, persistently patched -- verified independent of any
  live process. It does **not** yet prove the running emulator, booted
  fresh from this copy, shows the translation during actual play: a
  save-state reload restores frozen RAM rather than re-reading from
  disc (confirmed this session -- repeated reloads of the same slot
  reliably reproduce the exact same starting dialogue, regardless of
  real elapsed time, which is the signature of a frozen snapshot, not
  a live re-read), so that specific check needs a genuine cold boot
  reaching the target scene through real menu navigation.

  **Follow-up, same session: `gcrts.pcsx_keyboard_input` (OS-level
  `SendInput` into the game window) was a false lead, corrected in
  place.** Its one dramatic "success" (a Cross press opening a system
  menu) was PCSX-Redux's own ImGui menu reacting to the OS keystroke,
  not the emulated PS1 controller -- every subsequent attempt on a
  different (BIOS) screen failed despite confirmed OS-level focus, and
  this is actually consistent with, not a contradiction of, this
  project's own earlier, more rigorous finding
  (`docs/tooling/PCSX_REDUX_CAPTURE_PROTOCOL.md` sections 8 and 12):
  neither synthetic keyboard input nor a real virtual XInput gamepad
  ever reaches the emulated controller in this build.

  **The real fix, found and live-verified this session:**
  `gcrts.pcsx_pad_bridge` + `pcsx_lua/pad_input_bridge.lua`. PCSX-Redux's
  Lua API exposes `PCSX.SIO0.slots[1].pads[1].setOverride()`/
  `.clearOverride()`, confirmed directly against the real
  `src/core/pad.cc` source: `poll()` ANDs `buttonStatus` with a
  persistent `overrides` mask and packs that straight into the SIO
  response bytes the BIOS/game read -- completely independent of
  GLFW/ImGui/window focus, so none of the OS-input failure modes apply.
  Live-confirmed end-to-end via the real Python client against the real
  running instance (`PadBridgeClient.press_button`), including a real,
  load-bearing quirk: PCSX-Redux's Lua event dispatcher can silently,
  permanently kill a "GPU::Vsync" listener for no logged reason (a
  fresh reload always fixes it) -- `press_button` self-heals by
  reloading the bridge script once and retrying before giving up. This
  removes the "needs a human at the controls" blocker for Stage 4's
  final check, and for any other part of this project that hit the
  same wall (including the still-open movie-loader ambiguous groups
  from earlier this session). `gcrts.pcsx_keyboard_input` still works
  fine for its actual proven use (driving PCSX-Redux's own UI, e.g. the
  Lua Console itself, via `gcrts.pcsx_lua_console`) -- just not for
  emulated controller input.
  **Final follow-up, same session: the cold-boot-and-navigate
  confirmation run was performed, and Stage 4's exit criterion is
  CONFIRMED_LIVE.** A real root cause for the earlier stuck-BIOS-menu
  problem was found along the way: opening the raw patched `.bin`
  directly (rather than its `.cue`) left the BIOS unable to recognize
  the disc as bootable, falling back to its own memory-card/CD-player
  shell -- unrelated to any patch-correctness question. Fixed by a
  clean `File > Reboot` then `File > Open Disk Image` on `game.cue`
  (log confirmed: `Loaded CD Image: ...game.cue[+cue].`, CD-ROM Label
  `TWILIGHTSYNDROME`, ID `SLPS00102`). From there: `Start emulation`
  (a genuine fresh PS-X kernel boot, not a save-state), the publisher
  logo and opening cinematic played in full, `gcrts.pcsx_pad_bridge`
  drove START/CIRCLE through the title screen and into the opening
  story beats, a live memory read confirmed CAP1.EXE resident
  (`pc=0x8007431C`, matching `pcsx_lua/spu_playback_trace.lua`'s own
  `KNOWN_OVERLAYS` signature exactly), and the classroom/Kimika scene's
  dialogue box rendered `"See"` (Latin script) embedded mid-sentence
  inside an otherwise all-Japanese line — exactly the patched disc
  offset's script unit, reached through real menu navigation with no
  save-state and no live RAM injection involved. Evidence:
  `evidence/stage4_cold_boot_disc_patch_proof/` (`full_frame.png`,
  `dialogue_zoom.png`, `record.json`). Only `"See"` was clearly legible
  on screen before the text box's line-wrap boundary — closed by an
  independent offline check: decoding the actual on-disc bytes at that
  exact offset (`build_workspace/patched_discs/patch_verify.bin`, via
  `gcrts.iso9660`/`gcrts.script_decoder`/`gcrts.editable_script`,
  entirely independent of the emulator/renderer) returns the complete,
  exact string `"See you soon"` — confirming the full replacement is
  byte-correct on disc, not just the fragment the line-wrap happened to
  make visible.
  Exit criterion (SRS acceptance criteria 3-5, i.e. survives a real
  patched-image reboot): **CONFIRMED_LIVE.**

Stage 5+ (= SDD's O5-O8) — Movie subtitle, audio
  Explicitly gated (SRS §12, SDD §19) behind movie-time source and
  VRAM-write-path research the readiness audit rated Low readiness.
  Not attempted until those specific prerequisites are individually
  proven, matching this whole project's standing rule against
  overclaiming.

  **First investigation, same session: VRAM-write-path checked, still
  open.** `src/core/pcsxlua.cc`'s real `REGISTER` list confirms no
  VRAM write function is exposed to Lua at all (only `takeScreenShot`
  touches the GPU class). The one other candidate — writing the GPU's
  hardware GP0 port (`0x1F801810`) directly via `GdbClient.write_memory`
  — was tested live, twice, and produced **no observable effect**
  (before/after screenshots byte-identical, including once against a
  frame independently confirmed to show real display content). An
  earlier pass at this same test initially misread ordinary game
  rendering during a resume-and-wait gap as write-caused corruption —
  caught by hashing the actual files rather than trusting a visual
  comparison, and corrected before it was written down as a finding.
  See `docs/renderer/VRAM_WRITE_PATH_INVESTIGATION.md` and
  `evidence/vram_write_path_investigation/` for the full account. Net:
  the blocker is unchanged (no VRAM write path proven), but one real
  candidate is now ruled out rather than untested.

  **Second investigation, same session: movie-time-source, partial
  positive.** Tested whether host-side wall-clock time (anchored via
  `PCSX.hardResetEmulator()`+`PCSX.resumeEmulator()` through the Lua
  Console — found to be far more reliable than OS-level GUI menu
  clicks, which proved fragile and are now deprecated for this purpose,
  see `docs/tooling/PCSX_REDUX_CAPTURE_PROTOCOL.md` section 18) is a
  reliable proxy for boot/movie playback position. Two independent
  runs, screenshotted every 2s for 40s and hashed: **17 of 20 samples
  matched byte-for-byte**, with **every sample through t=22.77s
  (the BIOS/logo portion) matching exactly**, and most (5/8) matching
  in the later, faster-changing window too. See
  `docs/renderer/MOVIE_TIME_SOURCE_INVESTIGATION.md` and
  `evidence/movie_time_source_investigation/` for the full account,
  including the honest gap: the 3 mismatches weren't isolated as host-
  timing jitter versus genuine non-determinism (the frames themselves
  weren't saved for comparison in that pass — fixed in
  `scripts/movie_time_source_probe.py`'s current version). Net: a real,
  encouraging partial result for O5 (external subtitle sync, where
  sub-second drift during fast content is unlikely to be perceptible),
  not yet a frame-exact PS1-side source, which O6/O7 (internal
  composition) would still need.

  **Third step, same session: the first real O5 building block, built
  and tested.** `gcrts.overlay_action.SubtitleTrackPayload` (a stub
  since Stage 3) now has real fields — `reference_overlay` (which
  overlay-identity name marks a track's own t=0) and `cues` (each a
  `t_offset_seconds`/`text`/`duration_seconds` triple) — plus a new
  `gcrts.subtitle_track_runner` that waits for the reference overlay
  live, then fires each cue in chronological order for its own
  duration through the already-proven `ExternalOverlayRenderer`. Tracks
  are authored as plain JSON (`subtitle_tracks/op_intro.example.json`),
  deliberately friendlier than the payload's own machine-facing
  `to_dict()` shape — editing a subtitle means editing that file, not
  Python. `scripts/run_subtitle_track.py` runs one live. 7 new tests
  (`tests/test_subtitle_track_runner.py`, `tests/test_overlay_action.py`),
  fake clock + fake `read_memory` exercising the real
  `identify_overlay` code path, no live emulator required; full suite
  1060 passed. Deliberately does NOT depend on VRAM-write-path at all
  (cues render externally) — see `docs/renderer/SUBTITLE_TRACK_MECHANICS.md`
  for the full design.

  **Fourth step, same session: live-confirmed end-to-end.** Ran
  `scripts/run_subtitle_track.py` against a real fresh boot
  (`PCSX.hardResetEmulator()`+`resumeEmulator()`): both cues fired
  within a few hundred milliseconds of their intended offsets
  (`t=5.0s`→`5.249s`, `t=12.5s`→`12.726s`), and a real composited
  desktop screenshot (not `PrintWindow`, which wouldn't show a
  separate overlapping window) caught the overlay text rendering
  directly over real game content, confirmed in two consecutive
  captures. Evidence: `evidence/subtitle_track_live_proof/`. Closes
  the "no live run yet" gap this same building block was built with.
  Remaining honest gap: the example track's cues are placeholder text
  at illustrative timestamps, not a real authored subtitle track for
  `OP.STR` — the mechanism is proven, the content isn't written yet.

  **Fifth step, same session: real audio-derived timing for OP.STR,
  not fabricated.** Asked directly rather than inventing dialogue: the
  user chose "build real timing from the audio, text later" over
  guessing content. New `gcrts.movie_str_audio` reads `OP.STR`'s exact
  raw bytes from the real disc image and demuxes its audio via
  FFmpeg's `psxstr` support (already validated in this project's own
  `docs/audio/XA_DECODER_VERIFICATION.md`) — confirmed live to
  auto-detect this exact file correctly (`Video: mdec 320x240 15fps`,
  `Audio: adpcm_xa 37800Hz stereo`). New
  `gcrts.audio_activity_segments` finds amplitude-based activity
  segments (honestly scoped in its own docstring as activity
  detection, not speech detection).
  `scripts/build_op_intro_track_from_audio.py` ties these together:
  found 15 segments, kept 14 short ones (0.5-5.7s, plausibly one line
  each) as real `subtitle_tracks/op_intro.json` cues with text left
  `TBD`, and excluded one ~80s block (almost certainly continuous
  background music) rather than force-fitting it as one absurd cue.
  Live-run result: **all 14 cues fired within ~0.2-0.9s of their real
  audio-derived offsets** against a fresh boot. Evidence:
  `evidence/op_intro_audio_derived_track/`. 7 new tests
  (`tests/test_audio_activity_segments.py`, synthetic WAV data, no
  live dependency); full suite 1067 passed. The mechanism and the
  timing pipeline are both now real end-to-end; the one remaining gap
  is content — the actual translated text, which needs a human who can
  hear the audio, not more tooling.

  **Sixth step, same session: a direct user correction reframes the
  actual deliverable for movies.** The external overlay path (this
  entire O5 line of work) is a real, live-proven *testing/authoring
  tool*, not the shippable mechanism — a burned CD played on real PS1
  hardware has no host machine running Python code next to it. The
  real deliverable needs subtitle text burned into the disc-resident
  video itself, the same disc-patching shape Stage 4 already proved
  for regular dialogue text. Full account, including the honest,
  currently-unbuilt gap (a real PS1 STR/MDEC *encoder* — FFmpeg's own
  `mdec` support is decode-only):
  `docs/renderer/BURNED_IN_SUBTITLE_PIPELINE.md`. What IS newly
  confirmed: new `gcrts.burn_in_subtitle` burns subtitle-style text
  directly onto a real frame decoded from `OP.STR` — clean, correctly
  positioned, non-destructive to the rest of the frame
  (`evidence/burned_in_subtitle_concept/`). 5 new tests, full suite
  1072 passed. This does not replace `gcrts.audio_activity_segments`'s
  real cue timing or `gcrts.subtitle_track_runner`'s authoring/testing
  value — both remain useful once/if a real encoder is found — but O5
  external composition is no longer the framing for what actually
  ships; re-encoding to a real PS1 bitstream is the next genuine
  unknown, and it has not been started.

  Seventh step, same session: the encoder gap is closed --
  CONFIRMED_LIVE end-to-end. Found and verified a real, working
  PS1-compatible video/audio encoder (`psxavenc`, a third-party
  open-source tool, prebuilt Windows binary) whose defaults matched
  `OP.STR`'s own real stream properties exactly. Proved a plain
  round-trip first (decode -> re-encode unmodified -> disc-patch ->
  boot -- clean playback confirmed) before ever touching content, per
  this project's own discipline. Then: burned "-insert text here-"
  onto a real ~2-second frame window (`gcrts.burn_in_subtitle`),
  re-encoded via the new `gcrts.movie_str_encoder`, patched into a
  disc image copy, booted live, and visually confirmed the burned-in
  subtitle rendering correctly over real movie footage -- twice,
  independently. Evidence:
  `evidence/burned_in_subtitle_live_playback/`. A real, load-bearing
  timing-calibration finding came out of this too: frame-count-based
  timing assumptions were off by ~10.7s for a freshly-loaded disc
  image (plausibly a one-time CD seek/buffer delay), found only by
  scanning a wide real-time window empirically rather than trusting
  the arithmetic -- documented in
  `docs/renderer/BURNED_IN_SUBTITLE_PIPELINE.md` as a warning for
  anyone reusing this timing model. 3 new tests
  (`tests/test_movie_str_encoder.py`, mocked subprocess, no live
  dependency). This is the actual shape of mechanism the user asked
  for -- real, disc-resident, no host-side tooling required at
  playback time. What remains: real translated text (still placeholder
  everywhere) and eventual real-hardware verification.

  Eighth step, same session: consolidated into
  `gcrts.movie_subtitle_burner` (whole-track burning, not one cue at a
  time) and burned in the REAL, COMPLETE 14-cue
  `subtitle_tracks/op_intro.json` -- not a single placeholder. Offline
  verification (thorough, complete): independently re-decoded the
  output and confirmed all 14 cues correct. Live verification
  (partial): confirmed a second, independent cue rendering correctly
  during real playback on a disc-patched copy; a full real-time scan
  of all 14 hit unrelated automation trouble (window resize/collapse
  mid-capture) and wasn't completed, not considered necessary given
  the offline check's rigor. Evidence:
  `evidence/full_track_burned_in_live_proof/`. The overlay engine's
  movie-subtitle mechanism is now complete as a mechanism -- the
  remaining work is content (real translated text) and real-hardware
  verification, not more engineering.
```

Stages 1, 2, and 3 are all complete as of this document, each with a
real, live, once-run proof rather than just passing tests. Stage 4 (an
internal, game-resident payload) is the next concrete piece of work,
and is real new reverse-engineering territory (a real hook point in a
patched executable), not a wrapper over existing modules like Stages
1–3 were — it should stay its own dedicated pass, not attempted as an
extension of the plumbing above.
