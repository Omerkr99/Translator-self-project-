# Current System Status

This document is the single current source of truth for the GCRTS project
(reverse-engineering and live-editing toolkit for *Twilight Syndrome:
Tansaku Hen*, SLPS-00102). It describes the system **as it exists right
now** — not how it got here. For investigation history, method-by-method
dead ends, and the full evidence trail behind any claim below, see the
dated logs: `RENDERER_LIVE_PROOF.md`, `RENDERER_1_RUNTIME_DRIVER.md`,
`RUNTIME_ASSET_TRACKER.md`, `GPU_OT_RUNTIME_MAP.md`,
`GLOBAL_SELECTION_MODEL.md`, `VISUAL_INSPECTOR_ARCHITECTURE.md`,
`RUNTIME_SNAPSHOT.md`, `USER_CONTROLLED_PAGES.md`,
`ASSET_INSPECTOR_ARCHITECTURE.md`, `IMAGE_ASSET_STATUS.md`,
`BACKLOG_INVESTIGATION_RESULTS.md`, `DISC_FILE_CATALOG.md`.

## Headline

- **Test count**: 815 passed, 0 failed (`py -m pytest tests/ -q`), ~20s.
  97 modules in `gcrts/`, 79 test files.
- **Strongest completed capabilities**: the live HOST_FITTED text
  editing/injection pipeline (this is what actually renders edited
  dialogue today); Renderer 1's position mechanism, now with an
  automatic runtime driver (profile-validated capture, descriptor
  application, atomic rollback) instead of manual debugger work; a
  full Runtime Asset Tracker + Visual Inspector + Global Selection +
  Pause Snapshot + User Pages stack that turns "what is on screen right
  now, and is it *actually* drawn vs. merely resident in VRAM" into a
  live, queryable, GPU/OT-correlated answer instead of a screenshot
  guess; a complete, live-verified script-cue → physical-disc-sector
  audio trace, extended to a full live-verified playback lifecycle
  (START/PLAYING/position/STOP), general LBA-to-file source resolution,
  a proven script-occurrence-to-audio-event correlation (which exact
  dialogue line owns which physical audio, not just which cue number),
  and now the actual causal mechanism that selects the source (a
  previously-hidden control-word selector, traced through a real
  function-pointer dispatch table) plus a first, honestly-scoped
  audio-captioning layer — all wired into `RuntimeSnapshot`; a genuinely
  persistent (survives a fresh boot, not just a save state) disc-level
  asset edit.
- **Biggest engineering gap**: profile coverage. Almost everything that
  works live (Renderer 1, the sound-cue/audio-lifecycle chain, the OT
  roots) is proven against exactly one or two loaded executables out of
  15 on the disc; the registry (`mips_patch_profiles.json`) marks the
  rest `unverified`. Nothing here is a code defect — it's unfinished
  per-overlay onboarding.
- **Biggest reverse-engineering gap**: how `.STR` movie playback is
  actually triggered and driven. This blocks Stage B/E/F of the
  backlog (movie detection, subtitles, pause-to-subtitle workflow) as a
  single dependency chain; the audio side (Stage D) now has a real,
  live-verified lifecycle for one cue, independent of movie detection.
- **Recommended next milestone**: identify which overlay executable is
  actually resident during movie playback (concretely: retarget the
  `dma_channel_start` live trace at a `CAP*.EXE` address instead of
  `PROG.EXE`, or trace the boot/overlay-loader chain itself) — this is
  the one open question blocking the movie/subtitle backlog thread.
  Separately, for audio: the causal source-selection mechanism is now
  **fully resolved and triple-cross-validated** (`AUDIO_CONTEXT_RESOLUTION.md`,
  `XA_STREAM_RESOLUTION.md`) — three independent live mechanisms (playback
  position, selector-table lookup, and a real event-descriptor structure)
  all agree exactly on the resolved file. The low-level CD-ROM driver
  itself is now also identified and live-hardware-verified
  (`gcrts.cdrom_driver_map`, `XA_STREAM_RESOLUTION.md`'s own
  "XA Channel / Filter Runtime Resolution" follow-up): the real
  `0x1F801800`-`0x1F801803` register map, the shared command-issuing
  routine, and the real Setfilter command number (`0x0D`) are all
  confirmed. **A real, live, reproduced Setfilter call has been
  caught** (`gcrts.cdrom_setfilter`, `XA_STREAM_RESOLUTION.md`'s "Capture
  the Real CD-XA Setfilter Command" follow-up): `file=2, channel=1`,
  identical across two independent captures, `file=2` cross-validated
  against the real disc catalog. The earlier "zero hits" result turned
  out to be a real bug (wrong stack offset, silently returning a
  plausible-but-wrong `0x00`), found and fixed via a static scan rather
  than repeating the same live technique — documented honestly, not
  glossed over.
  **Important correction (`AUDIO_EVENT_EXTRACTION.md`)**: a follow-up
  live re-check, this time reading the position counter and playback
  state at the exact same instant as the Setfilter hit (closing the gap
  flagged above), found the call firing during a STOPPED state with a
  stale, unrelated `last_req_params` — twice, independently. This
  Setfilter is most likely a fixed default/reset value, **not proven to
  be any specific event's own channel selection**
  (`gcrts.cdrom_setfilter.is_proven_event_specific()` returns `False`,
  evidence attached). A read-only extraction backend
  (`gcrts.audio_event_extraction`) was built and tested regardless —
  it deliberately never defaults file/channel from that historical
  observation, so it's ready the moment a genuinely per-event channel
  source is found. The original file-open-consumer blocker (two
  systematic code searches, zero consumers of the constructed path
  string) is unchanged. `event_end_lba` also remains unresolved — no
  `PLAYING → STOPPED` transition was observed live this pass.
  **Follow-up (`CDROM_SETFILTER_CAPTURE.md`)**: a ~460-second live
  capture on the running game state, spanning real user-confirmed
  audible playback, found the "one cue, one Setfilter" model is simply
  wrong — 8 Setfilter hits, all identical `params=(2, 1)`, while the
  disc-seek target changed 5 times. The better-supported model is now
  **filter persistence**: one setting valid across many cycles
  (`gcrts.cdrom_setfilter.filter_appears_persistent()` → `True`).
  Separately, and importantly: the audio lifecycle state byte never
  transitioned to PLAYING during this entire confirmed-audible window —
  an honest caveat now recorded directly in `gcrts.runtime_audio`'s own
  module docstring, since this project's earlier PLAYING/STOPPED
  evidence, while real, is not shown to generalize to every real event.
  **Follow-up (`AUDIO_PLAYBACK_TRUTH.md`)**: decoded the real Setmode
  value from that traced command cycle (`0x01`) against public PS1
  documentation — XA-ADPCM and XA-Filter are both OFF. The entire
  `Setloc/Setmode/ReadN/Setfilter` cycle traced across three milestones
  was **never the audio path**, just a data-read loop. The documented
  XA-audio command (`ReadS`, `0x1B`) has never been observed in any
  capture. A widened static scan found no new command-issuing site. The
  real audio-configuring code path remains genuinely unfound —
  `gcrts.audio_playback_truth.AudiblePlaybackState` exists with exactly
  one honest member (`UNKNOWN`), not a forced/unverified `AUDIBLE_XA`.
  **Follow-up (`XA_PLAYBACK_PATH.md`)**: a second live session (save
  slot 9 reloaded while armed, user-confirmed trigger) again produced
  zero `ReadS` hits. Checked the real disc's own `.cue` file directly —
  exactly one track, `MODE2/2352` — and found genuine CD-DA playback is
  **structurally impossible** on this disc, ruling that fallback
  hypothesis out completely (`gcrts.xa_playback_path.PLAYBACK_PATH_HYPOTHESES`
  records all 6 hypotheses the milestone required checking, each with
  real evidence). The traced `ReadN`/Setmode cycle is now permanently
  `RULED_OUT_AS_XA_AUDIO_PATH`. The real path remains open — most likely
  reachable only through a second, still-unfound command-register
  pointer-variable set distinct from the one 3 known sites all share.
  **Follow-up (`CDROM_DRIVER_DISCOVERY.md`)**: found that second kind of
  set — a full live-RAM value scan (not a code-pattern scan) found 7
  additional complete CD-ROM register pointer sets. Traced the 3 in the
  known set's own page and found they belong to a generic
  interrupt/DMA dispatch table (GPU, MDEC, CD-ROM, and PIO channel
  addresses together, plus `I_STAT`/`I_MASK`) — real, verified, but not
  a second command-issuing audio driver
  (`gcrts.cdrom_driver_discovery.any_new_command_driver_confirmed()` →
  `False`). **Follow-up (`SPU_AUDIO_PATH_DISCOVERY.md`)**: pivoted to
  the SPU side as suggested. A full-RAM value scan for the SPU base
  address found 7 pointer holders; the one adjacent to the known
  CD-ROM block led to a real, live-firing, debug-string-named `CD_init`
  function (`0x80081B04`, `"CD_init:addr=%08x\n"`) that sets SPUCNT to
  `0xC001` — psx-spx documents bit 0 as "CD Audio Enable" for both
  CD-DA and XA-ADPCM. Confirmed live across two sessions (6 firings, 9
  static call sites) — the strongest concrete anchor this whole
  investigation has produced. Not yet a full answer: the write never
  persisted on a later read, and a 300s combined watch (also covering
  the 2 real SPU Key ON writer sites found the same pass) caught
  neither `CD_init` re-firing nor a real non-empty Key ON bitmask
  alongside a confirmed audible trigger.
  `gcrts.spu_audio_path.classify_playback_backend()` honestly returns
  `UNKNOWN`. **Follow-up (Live Audible Trigger Correlation)**: ran that
  exact session. The user explicitly confirmed a real audible voice
  line during a captured window where **zero of the 6 armed sites
  fired** — a decisive negative, ruling out `CD_init` and both Key
  ON/OFF families as the mechanism for that instance. Separately
  discovered, via a direct write-then-readback diagnostic while
  genuinely running, that GDB's own memory access to the SPU hardware
  I/O range does not round-trip at all in this environment
  (`gcrts.spu_audio_path.spu_mmio_read_write_roundtrip_reliable()` →
  `False`) — reclassifying every prior "SPU register reads back 0"
  observation as tooling-limited, not a confirmed game-behavior fact.
  The real path is still open; the blocker has shifted from "no
  capture window" to "no reliable channel to observe true SPU hardware
  state" — next direction is finding one. **Follow-up
  (`SPU_OBSERVATION_CHANNEL.md`)**: found one — PCSX-Redux's own
  native SPU debugger (`Debug > SPU > Show SPU debug`), validated
  against a real state change. Cross-checked at the same live instant:
  GDB read SPUCNT as `0x0000` while the native tool showed
  `CTRL=0xC081` (CD Audio Enable set) — GDB was simply wrong about
  that one register. A silent-vs-audible comparison found CD Audio
  Enable identically set in both a post-load baseline and a
  user-confirmed-audible capture — a persistent, always-on state, not
  a per-line toggle. Could not isolate one SPU voice channel as the
  dialogue source, since background-music channels were already active
  in the "silent" baseline. Next direction: a scene genuinely free of
  background music, to retry the comparison cleanly.
  **Follow-up (Manual All-Voices-Muted Experiment) — playback backend
  resolved**: a virtual XInput gamepad (`vgamepad`/ViGEmBus) was tried
  first for reliable automated triggering — confirmed working at the
  Windows/XInput level, but the game itself never responded, so per
  this milestone's own time-boxing instruction the investigation
  switched to a manual fallback. Using the native SPU Debug window's
  per-channel Mute controls, the user manually muted every active SPU
  voice during a real, self-triggered dialogue line — the voice line
  kept playing, completely unaffected, reproduced independently in a
  second, structurally different scene.
  `gcrts.spu_audio_path.all_spu_voices_muted_dialogue_still_audible()`
  returns `True`. Dialogue audio does not go through the SPU's 24-voice
  mixing engine at all — it enters via the CD input path, the
  mechanism SPUCNT's CD Audio Enable bit gates.
  **`classify_playback_backend()` now returns `CD_INPUT_UNKNOWN_FORMAT`,
  not `UNKNOWN`** — the first confirmed (non-`UNKNOWN`) playback-backend
  classification this entire audio investigation has produced. Not
  `XA_ADPCM_CONFIRMED`: XA-ADPCM is the only realistic remaining
  candidate by elimination (CD-DA is structurally ruled out on this
  disc) but its exact format was not independently re-verified this
  pass. Next direction: confirm the CD input stream's format directly.
  **Follow-up**: chased that exact direction and found two more
  negatives without a positive confirmation. Of `CD_init`'s 9 call
  sites, 2 are gated by a genuine CD-position change-detection check —
  live-armed across a real, confirmed voice line (twice), neither
  fired. Separately, logged every `Setmode` value across ~150 real
  seconds spanning a confirmed voice line: 46 captures, 100% showing
  the XA-ADPCM bit off. `classify_playback_backend()` stays
  `CD_INPUT_UNKNOWN_FORMAT` (the routing finding is unaffected), but
  the software Setmode toggle this project can observe is evidently
  not how (or not the only way) XA-ADPCM decode gets enabled.
  **Follow-up (`AUDIO_TRANSPORT_PATH.md`)**: stopped chasing
  Setmode/`ReadS` entirely and asked what actually feeds CD Input
  instead. Found PCSX-Redux's native `Debug > Misc hardware > Show HW
  Registers` window (all 7 DMA channels' MADR/BCR/CHCR, reliably).
  With a save state at a confirmed voice-line moment and genuine
  execution verified (Timer 1's counter changing every frame), **DMA
  channel 3 (CD-ROM) and channel 4 (SPU) showed zero change across the
  entire window**, while DMA channel 2 (GPU) showed a real transfer in
  the same captures — ruling out "frozen emulator" and confirming a
  genuine negative.
  `dma_cdrom_or_spu_channel_active_during_confirmed_voice_line()` →
  `False`. Points to a direct hardware audio bus from CD-ROM to SPU CD
  Input, bypassing system DMA entirely. `TransportPath`/`StreamFormat`
  are now separate enums: `classify_transport_path()` →
  `DIRECT_HARDWARE_AUDIO_BUS`, `classify_stream_format()` → `UNKNOWN`
  (still open).
  **Follow-up**: tried to inspect SPU-internal RAM directly per the
  above's own next direction. Four avenues checked and closed — GUI
  Memory Editor windows (no memory-space selector), the native SPU
  Debug window (exactly 3 sections, no raw memory view), PCSX-Redux's
  documented Lua API (`getMemPtr`/`getParPtr`/`getRomPtr`/
  `getScratchPtr`/`getRegisters`/`getReadLUT` — none reach SPU RAM),
  and GDB's own SPU MMIO path (already unreliable on both address
  segments, closing the real-hardware-protocol fallback too).
  `spu_internal_ram_directly_inspectable()` → `False` — a confirmed
  tooling limitation. As a substitute, watched the SPU Debug window's
  own live `XA` panel (Frequency/Stereo/Samples/Volume L/R) across two
  60-frame captures, one with a trigger pinned to a precise 9-10s
  mark — every frame showed byte-identical values, zero correlation.
  `spu_debug_xa_panel_changed_during_confirmed_voice_line()` →
  `False`. Next direction: static/offline analysis (disassemble the
  actual decode routine, or inspect raw XAPACK sector bytes) rather
  than further live capture.
  **Follow-up (`XAPACK_FORMAT.md`) — the format question resolved,
  statically**: a byte-level scan of every audio sector across all 43
  real `XAPACK*.BIN` files found the exact standard Green Book CD-XA
  real-time-audio submode (`0x64`/`0xE4`) with `coding_info=0x01`
  (stereo, 37800 Hz, 4-bit ADPCM) — not inferred from the filename or
  the SPU Debug window, from the disc's own physical sector headers.
  `classify_stream_format()` now returns `XA_ADPCM` (previously
  `UNKNOWN`). Cross-validated against two real live LBA anchors already
  on record (`KNOWN_CUE_SOURCES[127]`'s `xa_channel=7`/LBA `126921`
  lands exactly inside channel 7's own physically-bounded stream in
  `XAPACK08.BIN`). Also found: strict 8-way channel interleave with a
  real, physical per-channel EOF marker (solving event segmentation
  without needing a live capture), a new `AudioAsset` stable-identity
  model (`gcrts.xapack`), a runtime bridge from `ScriptAudioAssociation`
  to `AudioAsset` (`gcrts.audio_asset_resolver`), and a working (raw +
  decoded-WAV) extraction pipeline — decode math is high-confidence,
  but the exact nibble-interleave layout has not been perceptually
  verified (no audio playback in this environment), an explicitly
  flagged, honest gap.
  **Follow-up (`XA_DECODER_VERIFICATION.md`) — that gap closed against
  an independent reference decoder**: got FFmpeg locally (via the
  `imageio-ffmpeg` PyPI package, an independent binary), fed it the
  exact real disc bytes for `XAPACK08.BIN` via its `psxstr` demuxer
  (which auto-detected the same 8-channel/stereo/37800Hz structure this
  project found by hand), and diffed its `adpcm_xa` decoder's output
  against this project's own sample-for-sample. First result: only
  1.44% agreement — a real failure, not "close enough." Reading
  FFmpeg's own open-source decoder directly (not a paraphrased summary)
  found two real bugs: wrong header byte offsets (4-11, not 0-3) and
  wrong nibble-to-channel assignment (low/high nibble = Left/Right at
  the same time position, not two sequential samples of one unit). A
  third bug (mono streams unhandled) was found via multi-asset testing
  and fixed too. After all three fixes: **100.0000% exact sample
  match, zero mismatches**, across 5 real assets (3 packs, stereo and
  mono). `decoder_verification_status()` → `REFERENCE_VERIFIED`.
  `AudioAsset` now exposes `decode_confidence`/`decode_supported`/
  `pcm_sample_count`, and a safe playback/export backend exists
  (`decode_audio_asset`/`export_audio_asset_wav`). Only perceptual
  (by-ear) confirmation remains open — no audio playback available in
  this environment.
  **Follow-up (`SEMANTIC_AUDIO_CLASSIFICATION.md`) — a new, fourth
  layer**: knowing the physical format (`XA_ADPCM`, verified) says
  nothing about a channel's semantic role (dialogue/music/ambience/
  silence) — that gap is now closed by `gcrts.audio_semantic`
  (relative, within-pack feature classification — never claims
  `CONFIRMED`, only a `HEURISTIC` candidate score),
  `gcrts.semantic_label_store` (permanent, human-in-the-loop
  confirmed-label persistence), and `gcrts.audio_review` (per-pack
  review folders: WAV + `analysis.json` + `ranking.csv` +
  `review.html`, built so a human can confirm a channel's role in
  under a minute). A sanity check against the one already-confirmed
  asset (`XAPACK08:7`) caught a real classifier bug (high variance
  from a *regular* rhythmic loop was conflated with genuine speech
  burstiness — fixed via a new `burst_regularity_cv` feature) and
  surfaced a real, accepted limitation (envelope heuristics work well
  for short clips, not long sustained dialogue — that needs the
  runtime-anchor cross-check or direct listening instead).
  `XAPACK08:7` is now the project's first persisted confirmed semantic
  label (`DIALOGUE`, `USER_LISTENING`).
  **Follow-up (`FANDUB_REPLACEMENT_TEMPLATE.md`)**: the fourth
  (product access) layer's first real piece — `gcrts.audio_replacement`
  builds a `FandubEntry` template (original audio metadata pre-filled,
  translation/replacement fields empty) and rules-only
  `validate_replacement()` (format/clipping/silence/duration checks,
  never resampling or re-encoding). Gated on a confirmed semantic
  label — refuses to scaffold a project for anything not already
  `USER_LISTENING`/`RUNTIME_EVIDENCE` confirmed, including a bare
  `HEURISTIC` guess. `XAPACK08:7` has the project's first real
  scaffolded template. No injection/encoding implemented — explicitly
  out of scope until this foundation is exercised on more assets.
  A second confirmed asset, `XAPACK22:7`, was added via real live LBA
  captures (including one at `t=0.0s`, a strong timing anchor) plus
  direct listening confirmation; its Fandub template carries a real
  screenshot-sourced Japanese transcript and a draft (unreviewed)
  translation, with an honest caveat that the transcript's exact
  moment-of-belonging (this line vs. the preceding screen) is not yet
  human-verified.
  **Follow-up (`DIALOGUE_DATABASE.md`)**: built the unified
  `gcrts.dialogue_database` module — the project's own prioritized
  "Fandub Management Layer" Phase 1 — combining physical identity
  (`gcrts.xapack.AudioAsset`), the confirmed/unconfirmed semantic label,
  and any scaffolded Fandub template into one `DialogueDatabaseEntry`
  per asset, with a `DialogueWorkflowStatus` that is always *derived*
  from which fields are actually filled in (never asserted ahead of
  real progress) and never regresses past `RECORDED`/`AUDIO_VALIDATED`/
  `READY_FOR_INJECTION` once a caller sets one of those (external
  actions this module can't infer on its own). Evidence is a plain,
  additive list of real factual strings, never auto-generated. Both
  confirmed assets are now real entries: `XAPACK08:7` at `DETECTED`
  (no transcript/translation filled in yet), `XAPACK22:7` at
  `TRANSLATION_DRAFT` (real transcript + draft translation, neither
  verified nor approved). 22 new tests; full suite 753 passed, no
  regressions.
  **Follow-up (`LIVE_AUDIO_INSPECTOR.md`)**: the second of the
  roadmap's three named next priorities. `gcrts.live_audio_inspector`
  adds no new resolution logic — it chains the already-working LBA
  resolver and the Dialogue Database into one `LiveAudioInspection`
  per poll, wired into `RuntimeVisualProvider.last_live_audio_inspection`
  and displayed as a `NOW PLAYING: <asset_id> [state] <semantic type>
  -- <workflow status>` line at the top of the Visual Inspector's audio
  panel. Its one deliberate write — auto-registering a brand-new asset
  as `DETECTED` the first time it's ever resolved — is guarded to never
  touch an entry that already exists, so a human's hand-added evidence
  can never be silently overwritten by a later poll (regression-tested,
  and independently reconfirmed live: `git diff` on the real database
  file showed zero changes after 10 live polls against an
  already-known asset). **Live-verified against the actually-running
  emulator this session**: 10 consecutive real polls all resolved to
  `XAPACK22:7`, correctly showing its real `DIALOGUE`/`TRANSLATION_DRAFT`
  entry. 13 new tests; full suite 766 passed, no regressions.
  **Follow-up (`SUBTITLE_EXPORT.md`)**: the first real product-access
  deliverable, deliberately text-only (subtitles before dubbing, per
  request). `gcrts.subtitle_export` builds a standard `.srt` from a
  `DialogueDatabaseEntry`'s real translation, timed against the asset's
  own real `duration_seconds`; refuses to export anything without a
  translation already present, and a JSON sidecar carries an honest
  `transcript_verified`/`translation_approved` caveat rather than
  silently upgrading confidence. Caught and fixed a real data bug in
  the process: `XAPACK22:7`'s stored `translation` field already had
  the speaker prefix baked in from an earlier session, which duplicated
  once the separate `character` field was also prefixed for the
  subtitle line (`"ユカリ (Yukari): Yukari: ....Oh, right."`) — fixed at
  the source (both the Fandub template and the database entry), not
  papered over in the formatter; a note documenting the cleanup was
  added to the entry itself. Real output produced this session:
  `audio_export/fandub/XAPACK22_7/subtitle.srt` (`"Yukari: ....Oh,
  right."`, timed `00:00:00,000 --> 00:00:05,387`, the asset's own real
  duration). 15 new tests; full suite 781 passed, no regressions.
  **Retraction (2026-08-23)**: a fresh round of live save-slot-9
  captures produced 5 candidates (`XAPACK40:0`, `XAPACK22` channels
  0/1/2, and `XAPACK22:7` itself); direct listening rejected all 5,
  including `XAPACK22:7` -- its earlier confirmation was retracted
  (downgraded `USER_LISTENING` -> `UNVERIFIED` in the label store,
  `semantic_confirmed` set `False` on the database entry), with the
  original evidence preserved in the notes, not deleted. `XAPACK08:7`
  is unaffected (different investigation thread). This directly
  motivated the methodology shift below: current-LBA polling was
  retired as this project's primary identification technique.
  **Follow-up (`SPU_PLAYBACK_TRACE.md`) -- playback-first, not
  CD-first identification**: built `gcrts.spu_playback_trace` (a
  structured JSONL event schema: `SPU_KEY_WRITE`/`SPUCNT_WRITE`/
  `HEARTBEAT`/`SAVE_STATE_LOADED`/`MARK`, plus the full, psx-spx-
  verified per-voice SPU register map, internally cross-checked
  against this project's own already-verified `OFFSET_MAIN_VOL_L`)
  and `gcrts.spu_trace_analyzer` (marker-window filtering, voice-mask
  decode, and a `classify_playback_from_trace()` that names exactly
  one of `SPU_VOICE_PLAYBACK`/`CD_AUDIO_INPUT`/`OTHER_OR_UNKNOWN`/
  `NOT_YET_CLASSIFIED` with cited evidence, never a bare guess).
  Re-verified PCSX-Redux's real Lua API against its actual FFI source
  (`src/core/pcsxffi.lua`, `src/core/eventslua.cc`, fetched fresh this
  session) rather than trusting prior notes -- confirmed
  `PCSX.addBreakpoint`/`PCSX.getRegisters`/
  `PCSX.Events.createEventListener("Keyboard"/"GPU::Vsync"/
  "ExecutionFlow::SaveStateLoaded")` are real, and that the Lua memory
  API still has no SPU RAM/register accessor -- re-confirming, with a
  stronger primary-source evidence class, the already-established
  `spu_internal_ram_directly_inspectable() -> False` conclusion (not
  new information, independent corroboration). Built
  `pcsx_lua/spu_playback_trace.lua`, arming all 8 known writer sites
  from `gcrts.spu_audio_path` (cross-drift-tested against the Python
  constants) plus a marker via a real Lua `"Keyboard"` event listener
  -- genuinely different from the already-confirmed-broken "synthetic
  input into the emulated game controller" problem, since it only
  needs the host application to see a real physical keypress. **Not
  yet live-tested**: no tool available to this project can load/run a
  Lua script inside PCSX-Redux's GUI without a human action -- the
  first real run is the next experiment. 34 new tests (event
  schema/JSONL round-trips, marker-window filtering, voice-mask
  decode, classification logic per taxonomy value, a Lua/Python
  writer-site drift guard); full suite 815 passed, no regressions.

## Key current distinctions (do not lose these)

- **Screenshot-based mappings are fallback/evidence, never runtime
  truth.** Every subsystem below that reports "what's on screen" does
  so from live RAM/VRAM/GPU-packet correlation, with screenshots used
  only as human-facing confirmation or as a last-resort manual mapping
  when no live signal exists yet.
- **VRAM residency ≠ `DRAWN_THIS_FRAME`.** An asset can be uploaded and
  sit in VRAM long after the screen that used it is gone. The Runtime
  Asset Tracker's lifecycle states exist specifically to keep these
  apart; only assets whose primitives are actually found on the
  current frame's ordering table are ever reported as drawn.
- **Renderer 1 is structurally solved and now has an automatic driver**
  — but this is proven for one profile family
  (`SLPS00102_BASE_PROFILE`, one save-state lineage), not swept across
  every executable on the disc.
- **`.STR`'s container format is understood** (standard 7:1 Form1:Form2
  PS1 video/audio interleaving) — **runtime movie detection is not**.
  These are two separate claims; do not conflate "we know the file
  format" with "we know when/how the game plays it."
- **Audio source resolution (script cue → physical XA sector) is fully
  live-proven** for one control code. Playback *lifetime* (when it
  starts/stops, current playback offset) is not solved.
- **SDB2.0 has been located and identified** (real magic string
  confirmed in a real file) — its full frame/pixel structure is not
  solved, and there is no decode/PNG/edit capability for it.
- **Persistent disc-level asset modification has been proven** — a
  disc-image copy with a modified file and deliberately stale EDC/ECC
  booted correctly, fresh, with no emulator instrumentation. This is
  not yet equivalent to a real-hardware-validated rebuild; it has only
  been tested in PCSX-Redux.

---

## Subsystem detail

### Repository / test health — LIVE_VERIFIED

- 400 tests passing, 0 failing, full suite in ~15s
  (`py -m pytest tests/ -q --basetemp .test-tmp`; use `--basetemp` inside
  the workspace if the default Windows temp root lacks permissions).
- 70 modules in `gcrts/`; the great majority have dedicated test files.
- Git: repository has commits on `main`; large numbers of session/runtime
  artifacts (PCSX-Redux save states, memory card images, emulator
  config/shaders, Ghidra/debug scratch docs) live alongside the `gcrts`
  package in the repo root — none affect test health, but they mix
  project code with emulator-session working state.
- `README.md`'s test count is stale (predates most of this project's
  actual history); this document's count above is the current, verified
  number.

### Disc / BIN·CUE / ISO9660 / CDB container — LIVE_VERIFIED

- `gcrts.loader`, `gcrts.cdrom` (CD-ROM XA Mode2/2352 de-interleaving),
  `gcrts.iso9660` (real PVD + directory walk) all run against the actual
  636MB disc image, not just fixtures.
- `gcrts.cdb_codec`: the game's custom `.CDB` compression, ported from
  disassembly (`FUN_8007681c`), independently cross-validated against a
  separate third-party fan-translation toolkit's own from-scratch
  implementation (`rle.py`) — byte-for-byte the same control-code
  scheme. High confidence.
- Outer `.CDB` container (2048-byte page-offset/length table) confirmed
  against real files and against the third-party toolkit's independent
  format description.
- `DISC_FILE_CATALOG.md` is a full, current 117-entry real-disc listing
  (all files, LBA, size) produced by actually running `gcrts.iso9660`
  against the disc — not inferred.

### Compression — LIVE_VERIFIED

Single shared codec (`gcrts.cdb_codec`) covers every compressed stream
found so far: literal run / repeat-fill / LZ back-reference /
arithmetic-delta run / end marker. Used successfully for fonts, script
tables, `PROGHEAD.CDB`, `AFRM.CDB`, and MENUDAT/PROGDAT TIM streams.

### TIM / visual assets — IMPLEMENTED

- 4bpp indexed, 8bpp indexed, and 16bpp direct TIM all decode, encode,
  and round-trip. 4bpp/8bpp support full palette-preserving PNG
  import/export; 16bpp does not support indexed editing (not
  applicable to a direct-color format).
- Transparency is derived from the real CLUT value `0x0000`, not a
  hard-coded index guess.
- SDB2.0, SDB2.2, MS4, GP4, and TIM 24bpp remain **UNSUPPORTED** for
  decode/edit — see the SDB/MS/GP section below for what has and hasn't
  changed here.

### MENUDAT — IMPLEMENTED

- Full registry of all 32 independent 4bpp TIM streams in
  `DAT/SINKOU/MENUDAT.BIN;1`.
- Graphical browser/inspector with live-decoded thumbnails, search,
  metadata, palette/CLUT view (raw values + STP + usage counts), PNG
  export/replace, text replacement, a size-budget meter, deterministic
  exact-size re-encoding, temporary live-patch injection via the
  PCSX-Redux Web API, and restore.
- **LIVE_VERIFIED**: START/SETTINGS main-menu labels edited, injected,
  and confirmed rendering correctly in real gameplay, including
  surviving a hard reset (via the persistent disc-level route — see
  Persistent Build below) and the selected/unselected color-swap
  behavior. The exact color-selection *mechanism* (why the selected
  label goes bright and the other stays dark) is not identified, only
  observed.

### PROGDAT — IMPLEMENTED

- Full registry of all 15 PROGDAT streams; the main-menu classroom
  background is a confirmed 320×240 5-block composite.
- Same decode/edit/re-encode/export pipeline as MENUDAT.
- No composite-editing UI beyond what the registry + per-block tools
  already provide (a dedicated "PROGDAT composite UI" is not built).

### SDB / MS / GP formats — PARTIAL (identification only)

- **SDB2.0**: real sample located and magic-confirmed (`DAT/HITO/AFRM.CDB`
  decompresses to a stream starting `"SDB2.0 "`). A complete, confirmed
  18-entry frame/offset table follows the magic, with entries falling
  into three consistent size bands (real structural evidence of a
  multi-pose animation). The *outer* 512-entry directory table's general
  addressing scheme is not solved (one entry resolved via an ad hoc
  transform that does not generalize to the other 33). No decode-to-PNG
  or edit capability exists for SDB2.0 at any level.
- **SDB2.2 / MS4 / GP4**: still **UNKNOWN** — not located in any real
  file yet. `DAT/HITO/SIKFORM.CDB` shows a structurally similar
  directory-table pattern and is an unconfirmed candidate for one of
  these.
- TIM 24bpp: **UNSUPPORTED**, unchanged.

### Asset Inspector — IMPLEMENTED

Typed serializable asset descriptors; capability/status metadata;
`EXACT_CONSUMED_SIZE` / `MAX_ALLOCATED_SIZE` / `RELOCATABLE` / `UNKNOWN`
size policies; separate game-compression and TIM adapter layers; full
MENUDAT/PROGDAT registries; safe source/work/output/preview workspace
with a hash journal; CLI automation over the same backend as the GUI.
No full pixel-editor/undo stack; no automatic GPU-driven mapping beyond
what the Runtime Asset Tracker below provides.

### Runtime Asset Tracker — LIVE_VERIFIED

- Canonical lifecycle state machine (`UPLOADED_TO_VRAM` →
  `DRAWN_THIS_FRAME` → back to `UPLOADED_TO_VRAM` when no longer drawn →
  `UNLOADED`), asset identity based on provenance (never screen
  coordinates), VRAM region tracking with generation numbers that
  correctly demote an overwritten asset.
- `RuntimeVisualProvider` (the actual live-scanning path used by both
  desktop UIs) feeds every correlation hit through this state machine —
  previously it stamped everything `"DRAWN_THIS_FRAME"` unconditionally;
  this is fixed.
- Fails closed: an executable/profile that doesn't byte-match its
  recorded fingerprint returns zero live assets rather than guessing.
- Live-proven across two distinct real contexts in the same session
  (main menu: 3 assets; photos/spoils menu: 2 assets), including
  correct demotion of assets that stopped being drawn.
- Persistent Lua GPU breakpoints are **ruled out** for this PCSX-Redux
  build (both I/O-write and Exec variants eventually crash the
  emulator); production scanning uses read-only external RAM/VRAM
  snapshots only.

### VRAM / GPU correlation — LIVE_VERIFIED (scope-limited)

- Exact packed-texture-to-VRAM matching (row-exact TIM comparison, not
  approximate).
- GPU DMA trigger and OT-root addresses are live-confirmed for
  `PROG.EXE` specifically: DMA trigger `0x80049670`, OT root write
  `0x80049650`, four verified OT roots (`0x80076A24`, `0x80076A64`,
  `0x80075770`, `0x800757B0`).
- **Confirmed this project's own OT-root set and Renderer 1's `addPrim`
  (`0x800774B4`) are two genuinely separate systems**, live-verified in
  both directions (each fires with zero hits during the other's active
  window) — not a false unification, and not expected to unify, because
  the two loaded executables involved are never simultaneously resident.
  `addPrim` is ruled out as `PROG.EXE`'s own primitive-submission
  mechanism; `PROG.EXE`'s actual mechanism past the known OT-root/DMA
  pair is unidentified.

### Visual Inspector — LIVE_VERIFIED

- Single `scan()` call now merges Runtime Asset Tracker results and the
  Renderer 1 runtime driver's output, reusing one RAM snapshot for both
  (previously Renderer 1 output was never surfaced here at all).
- Hover/click hit-testing works against whatever is actually currently
  drawn, not just the static manual-mapping registry (previously a
  live-only object, like a Renderer 1 text line, could never be
  selected).
- Type/source-aware canvas coloring (image/raster vs. Renderer 1 text
  vs. candidate vs. manual-fallback) with a text label, not color alone.
- Manual rectangle mapping and a Translation View remain available as
  the explicit fallback/evidence tier, never treated as live truth when
  a runtime signal exists.
- Known scope limit, not a bug: this game never has a PROG.EXE menu
  asset and Renderer 1 text on screen in the same real frame (they're
  different loaded executables), so "both simultaneously visible" is
  only proven correct at the code level (a synthetic regression test),
  not demonstrated on live combined game data.

### Global Selection — LIVE_VERIFIED

Shared, file-based selection (`project_selection.json`) is now actually
consumed, not just published: the Asset Browser polls it and jumps to/
highlights/scrolls to the matching card and loads full state; the
Visual Inspector rings the selected object on canvas; selecting
something not currently drawn shows an explicit "known asset — not
currently drawn" message instead of silently doing nothing. Verified
live with deterministic scripted Tk sessions and real screenshots.

### Runtime Snapshots — LIVE_VERIFIED

`RuntimeSnapshot` (screen objects, tracker summaries, Renderer 1
profile/validation, an always-empty `active_movie` placeholder field —
deliberately not implemented yet, see Movies below — and `active_audio`,
which the Runtime Audio Tracker milestone turned into real, live data for
one confirmed voice cue, see Audio below) with save/load/diff
(`appeared`/`disappeared`/`changed`). Wired into the
Visual Inspector (Save / Load / Diff-vs-Saved buttons); Load turns off
live polling so loaded data isn't immediately overwritten. Live-verified
capturing a real dialogue scene, saving it, moving the emulator to a
different scene, then reloading and confirming the snapshot still shows
the original frozen data. Identity logic correctly covers both
asset-shaped and Renderer-1-text-shaped objects (an early version only
recognized `asset_id`-bearing objects and silently dropped all
Renderer 1 lines from diffs — fixed and regression-tested).

### User-controlled Pages / Scenes — LIVE_VERIFIED

`RuntimePageDetector.observe()` never assigns a name or promotes a
page's status on its own (pages are organization metadata, not runtime
detection). `create_named_page()` is the only function that names a
page or gives it an explicit boundary; `MatchingMode`
(`MANUAL_ONLY`/`STRICT`/`BALANCED`/`LOOSE`/`CUSTOM`) is inert until a
user picks one; `declare_variant()` links two compositions as one
conceptual page purely by user action, never inferred from similarity.
Wired into the Visual Inspector as a real dialog (name, matching mode,
required/optional/ignored asset lists). Live-verified: a real main-menu
scene was captured, named, had one asset moved to Optional via the
actual dialog, and the resulting page was confirmed correctly persisted
in `runtime_pages.json`.

### Renderer 1 (in-engine dialogue text) — LIVE_VERIFIED core, IMPLEMENTED driver, PARTIAL coverage

- **Position mechanism is structurally solved**: the live
  `CLD1`/`LayoutDescriptor` binary format drives real single- and
  two-line positioning, including center alignment resolved through the
  actual descriptor pipeline (not hand-picked). One-line, two-line, and
  single-character placement have all been live-modified and restored
  with visual confirmation.
- **Now has an automatic runtime driver**, not just manual debugger
  work: `gcrts.renderer1_profile` (`Renderer1Profile` +
  `validate_profile()`, which never trusts a hard-coded address without
  a live code-fingerprint match) and `gcrts.renderer1_runtime`
  (`capture_snapshot()` via one targeted memory read rather than a
  breakpoint loop, `build_overrides_from_descriptor()`,
  `apply_overrides_live()`/`restore_live()` with backup-verify-write-
  verify and atomic rollback on any failure).
- **Coverage is limited to one profile family**
  (`SLPS00102_BASE_PROFILE`), proven against one save-state lineage, not
  swept across the other 14 executables on the disc.
  `record_count=14` is the observed per-line wrap point for that
  profile; multi-line scenes beyond 14 total characters and the second
  double-buffered destination have not been separately exercised
  through the automatic driver.
- There is still no automatic "a dialogue is showing" trigger — a
  caller decides when to call `capture_snapshot()`.
- Glyph *content* selection (which character bitmap gets drawn) is
  handled by the separate, established HOST_FITTED live-injection path,
  not by the CLD1/position driver — the two are complementary, not
  unified into one custom-renderer path yet.

### Renderer 2 — BLOCKED

GTE/RTPS call site (`0x8004500C`) fired once during atmospheric
narration; its full position chain was never reproduced or fully
traced because the active overlay changed before the hit could be
captured again. No further live evidence beyond the one fired hit.

### CLD1 / layout descriptor — IMPLEMENTED

Binary format implemented and golden-byte-tested against its own spec;
`EditorLayoutPlan`/`layout_plan_builder`/`layout_preview` fully
implemented as data models; the encode → decode → live-apply chain is
now proven end to end through the Renderer 1 driver above (see that
section) rather than being a data-model-only proof.

### Script / font pipeline — LIVE_VERIFIED

- Script bytecode control codes: this project's own `script_decoder`
  plus a substantially more complete third-party fan-translation
  toolkit's independent decoder are cross-validated against each other
  and against live RAM captures (a specific finding —
  `pause_flag_a`/`Y_COLLECTION_MODE`'s trigger — matches the external
  toolkit's own `<PRESS,N>` command byte-for-byte, and both a live RAM
  scan and an offline full-script decode agree on the same rare-nonzero-
  parameter statistic).
- Font glyph decoding (two-level lookup, 16-color CLUT + 8×16 4bpp glyph
  bitmaps) is confirmed working via an actual run of the external
  toolkit's decoder against the real extracted `KFONT.CDB`, producing a
  correct, legible font atlas.
- `K0LINK.CDB` script-file indexing is confirmed working the same way —
  an actual run against the real disc file produced a complete,
  coherent 190-paragraph decoded script.
- Not yet done: porting/adopting this external-toolkit logic into
  `gcrts` proper (currently used as a verified external reference, not
  merged into `gcrts.script_decoder`'s own control-code tables or into
  a working `source="disk"` implementation for `script_unit`).

### Movies / `.STR` — PARTIAL (format known, runtime detection blocked)

- Container format is standard, confirmed PS1: `.STR` files use
  textbook 7:1 Form1:Form2 video:audio sector interleaving. No custom
  container reverse-engineering was needed.
- **Runtime detection is the open problem.** This session ruled out,
  with real live and static evidence, every hypothesis tried so far:
  - This game's own generic `.CDB` resource loader (`resource_load`,
    `0x8005342c`) — zero hits during a confirmed movie-playing window.
  - The confirmed sound-chain BCD MSF-to-LBA converter
    (`0x80080d54`) — zero hits during a confirmed movie-playing window.
  - Direct BIOS CD-ROM async calls (`jal 0xa0` with the function number
    in `$t1`, per the real PS1 BIOS calling convention) — a full static
    scan of all 15 disc executables for both possible call-site idioms
    found zero matches anywhere.
  - A generic DMA-channel-kickoff library function
    (`dma_channel_start(channel, madr, bcr, chcr, ...)`), found once per
    executable including the non-video boot stub — confirmed, on full
    decode, to be ordinary GPU-DMA boilerplate, not MDEC/movie-specific.
  - A live attempt to trace that function's channel argument during
    `PROG.EXE`'s copy specifically failed because `PROG.EXE`'s code
    never became resident at the expected address within the observed
    window — meaning `PROG.EXE` is likely not the overlay actually
    resident during movie playback (it shares a load-address range with
    several `CAP*.EXE` files, so this is an identity problem, not a
    dead end).
- **Concrete next step**: identify which overlay executable is actually
  resident during movie playback (retarget the same DMA-kickoff live
  trace at a `CAP*.EXE` address, or trace the boot/overlay-loader chain
  directly) before any further movie-specific tracing can proceed.

### Audio / XA / voice tracking — PARTIAL (lifecycle, occurrence identity, and causal source-selection all fully proven and cross-validated; downstream file-open mechanics, per-event xa_channel, event_end_lba, and position calibration remain open)

Full detail, evidence, and reproduction steps: `RUNTIME_AUDIO_TRACKER.md`
(lifecycle), `AUDIO_CUE_RESOLUTION.md` (source resolution),
`SCRIPT_AUDIO_ASSOCIATION.md` (which script occurrence owns which audio
event), `AUDIO_CONTEXT_RESOLUTION.md` (why that occurrence picks its
source), `XA_STREAM_RESOLUTION.md` (the constructed file path, a real
event-boundary structure, the honest file-open blocker, and the real
Setfilter capture), `AUDIO_CAPTIONS.md` (what is being heard),
`AUDIO_EVENT_EXTRACTION.md` (the read-only sector-extraction backend,
and the "Setfilter not proven event-specific" correction), and
`CDROM_SETFILTER_CAPTURE.md` (the ~460-second live session that found
the filter is most likely persistent, not per-cue), and
`AUDIO_PLAYBACK_TRUTH.md` (why `0x800A6107` is not audible-playback
truth, and the still-open search for what is),
`XA_PLAYBACK_PATH.md` (CD-DA structurally ruled out; the real path
still open), `CDROM_DRIVER_DISCOVERY.md` (7 additional CD-ROM
pointer sets found via a full RAM value scan, identified as
interrupt/DMA infrastructure, not a second audio driver), and
`SPU_AUDIO_PATH_DISCOVERY.md` (pivoted to the SPU side; found a
real, live-firing `CD_init` function that sets the documented "CD
Audio Enable" SPUCNT bit, then decisively ruled it and all known Key
ON/OFF sites out via a real user-confirmed audible correlation
experiment; separately confirmed GDB's own SPU-register read/write
path is unreliable in this environment), and `SPU_OBSERVATION_CHANNEL.md`
(found PCSX-Redux's own native SPU debugger; proved GDB's SPUCNT read
was simply wrong — CD Audio Enable is genuinely, persistently set on
real hardware, reversing the previous milestone's "write does not
persist" finding). `SPU_AUDIO_PATH_DISCOVERY.md`'s own follow-up
sections record the playback-backend resolution: a manual
all-voices-muted experiment found dialogue audio survives every
regular SPU voice being muted, proving it enters via the CD input
path — `classify_playback_backend()` is `CD_INPUT_UNKNOWN_FORMAT`, the
first non-`UNKNOWN` result this whole chain has produced. Finally,
`AUDIO_TRANSPORT_PATH.md` found that the confirmed audible dialogue
involves zero DMA activity on the CD-ROM or SPU channels, pointing to
a direct hardware audio bus bypassing system DMA — `TransportPath` and
`StreamFormat` are now modeled as separate concepts, transport
reasonably understood, format still `UNKNOWN`. Its own follow-up
section then closed the SPU-internal-RAM-inspection question as a
confirmed tooling limitation (GUI, Lua API, and GDB all checked and
exhausted) and separately ruled out the SPU Debug window's own live
`XA` panel as a dialogue-correlated signal via two precisely-timed
live captures — format remains `UNKNOWN`, with the recommended next
direction now static/offline analysis rather than further live
capture. **`XAPACK_FORMAT.md` then resolved the format question this
way**: a byte-level scan of every audio sector across all 43 real
`XAPACK*.BIN` files found the standard Green Book CD-XA real-time-audio
submode with `coding_info=0x01` (stereo, 37800 Hz, 4-bit ADPCM) —
`classify_stream_format()` now returns `XA_ADPCM`, cross-validated
against two real live LBA anchors. The same milestone built a stable
`AudioAsset` identity model (`gcrts.xapack`), a runtime resolver from
`ScriptAudioAssociation` to `AudioAsset` (`gcrts.audio_asset_resolver`),
and a working raw+decoded-WAV extraction pipeline. `XA_DECODER_
VERIFICATION.md` then closed the remaining decode-correctness gap:
diffed against FFmpeg's independent `adpcm_xa` decoder, found and fixed
two real layout bugs (header byte offsets, nibble-to-channel
assignment) plus a mono-handling bug found via multi-asset testing,
and reached **100.0000% exact sample match, zero mismatches** across 5
real assets. `decoder_verification_status()` → `REFERENCE_VERIFIED`;
only perceptual (by-ear) confirmation remains open. See
`AUDIO_ASSET_MODEL.md` for the data-model reference and
`XA_DECODER_VERIFICATION.md` for the full verification account.

- **Fully live-proven, every link actually captured, none inferred**:
  one script control code's complete call chain, from its literal
  inline parameter through 4 traced function layers to a specific
  physical disc sector — script cue (param 127) → `0x800760b4` (writes
  raw parameters to `0x800a6114`) → `0x80077808` (dispatches on a
  type/category value) → `0x80080d54` (BCD MSF-to-LBA conversion) →
  a real physical sector, confirmed via direct sector read: Form2 +
  Audio + Real-time submode (matching real `.STR` movie audio sectors),
  mono 4-bit ADPCM.
- **Runtime Audio Tracker milestone (`gcrts/runtime_audio.py`)
  LIVE_VERIFIED a complete three-state playback lifecycle**: `0x800A6107`
  (one byte of the previously-known "state pair" — its partner byte,
  `0x800A6106`, never changed in any observation) takes exactly three
  confirmed values — `0x00` STARTING (transient), `0x01` PLAYING
  (sustained 37-47+ real seconds, always co-occurring with the position
  counter below advancing), `0x02` STOPPED (sustained 57+ real seconds,
  position frozen, `0x800A6114` cleared to zero). Wired end-to-end into
  `RuntimeVisualProvider`/`RuntimeSnapshot` (`active_audio` is no
  longer an always-empty placeholder) and a minimal read-only panel in
  the Visual Inspector.
- **Audio Cue Resolution Generalization milestone
  (`gcrts/xa_disc_index.py`) corrected a wrong assumption in the
  original design, not just extended it.** The original plan was a
  small `script_parameter -> source` lookup table. Live evidence
  directly disproved that: the SAME raw script parameter (127),
  captured from independent fresh loads of the identical save state,
  resolved to LBAs in two DIFFERENT physical `XAPACK*.BIN` files. **What
  generalizes instead**: `source_file` is now resolved LIVE from
  whatever LBA is actually observed (`gcrts.xa_disc_index.
  resolve_lba_to_file`, an exact table of every `XAPACK*.BIN` file's
  real start LBA, read directly from the disc's own ISO9660 records) —
  correct for any position genuinely observed, not just the one cue
  Stage C originally traced. The old table (`KNOWN_CUE_SOURCES`) is
  kept only as a documented, last-resort fallback.
- **Script Context <-> Audio Dispatch Correlation milestone
  (`gcrts/script_audio_association.py`) found the actual explanation**
  for why the same parameter resolved differently: the live script
  buffer itself gets refreshed with new content between dialogue
  moments (already flagged as a real possibility by a prior session's
  `DECODER_READ_CURSOR.md`, now directly confirmed), and different
  refreshed loads can coincidentally share the exact same word offset
  and parameter while containing genuinely different dialogue. Proven
  live across 4 real samples: a content-based fingerprint of the owning
  `ScriptUnit` (not its position, not the raw parameter) changed exactly
  once and correlated exactly with which physical file got used, with
  no exceptions. `ScriptAudioAssociation.stable_key` (`script_source` +
  `ScriptUnit` id + control-code offset + content fingerprint) is the
  real, disc/script-provenance-based identity the original milestone
  brief asked for, deliberately never a raw RAM address. Wired into
  `RuntimeVisualProvider.last_script_association` and
  `RuntimeSnapshot.active_audio`'s new nested `"script_context"` field,
  live-verified through two independent code paths (direct GDB read and
  the Web API's bulk RAM dump) landing on the identical fingerprint for
  the same real dialogue.
- **Audio Context Resolution milestone (`gcrts/audio_context.py`) found
  the actual causal mechanism and closed it completely, correcting a
  real error from an earlier session.** The "127" inline parameter every
  prior pass (including this same session's own earlier work) treated as
  "the sound index" was never the real per-line selector — the
  `sound_or_voice_cue` control WORD's own low byte is (`0xc819` vs
  `0xc81a` for two of the known live samples — identical inline
  parameter, different low byte). A live breakpoint directly disproved an
  EARLIER session's own misidentification of this exact value
  (`BACKLOG_INVESTIGATION_RESULTS.md`'s Stage C trace had captured it and
  dismissed it as an unrelated per-frame tick counter). A first pass
  traced this through a 2-level table lookup to what looked like two
  different function addresses and stopped there, honestly flagged as
  unresolved — full disassembly then found those addresses aren't code
  at all: they're pointers into a literal, embedded, 9-entry filename
  string table (`"XAPACK08"`/`"XAPACK07"`/.../`"XAPACK00"`). The table1
  byte is the XAPACK file number directly, confirmed for all 9 possible
  values, not just the ones originally observed. **Now cross-validated**
  against the completely independent LBA-position-based resolver
  (`gcrts.audio_context.cross_validate_source`) on three live samples
  (selectors 25, 26, and a newly-caught 28) — all agree exactly.
  Corrected mid-session: an early version hard-capped the valid XAPACK
  number at 8 (based on only sampling the first 9 string-table entries);
  a real selector was then caught live resolving to `XAPACK09` and
  wrongly reported as unresolved. The table actually spans the disc's
  full real range (`XAPACK00`-`XAPACK42`, 43 files) — resolution is now
  validated against the real disc file list
  (`gcrts.xa_disc_index.resolve_filename_to_path`) rather than a guessed
  numeric bound, and correctly rejects plausible-looking but non-existent
  names (confirmed live: memory past the real 43-file table extent keeps
  producing well-formed "XAPACK43", "XAPACK44", ... text that isn't a
  real file).
- **XA File Open / Stream Resolution milestone (`gcrts/audio_stream_source.py`,
  `XA_STREAM_RESOLUTION.md`) traced one step further and found a THIRD
  independent confirmation plus a real, honestly-reported blocker.** The
  resolved filename gets built into a complete, live-readable ISO9660
  path string (`"\DAT\XA1\XAPACK09.BIN;1"`, standard `;1` version suffix)
  at a fixed address. What consumes that string to perform the actual
  file-open was NOT found despite two systematic searches (absolute
  address construction and `$gp`-relative small-data access, together
  covering ~576KB of loaded code) — reported honestly as a genuine
  blocker, not guessed at. Separately, found and confirmed a real "event
  start LBA" field in an adjacent, previously only partially-decoded
  structure (`0x800A61A8` -> `0x800A60EC+0x04`) — matches the real disc
  catalog exactly for two different files, live-verified. All three
  independent resolution mechanisms (playback position, selector-table,
  event-descriptor structure) now cross-validate exactly on live
  capture. `xa_channel` remains unresolved either way.
- **XA Channel / Filter Runtime Resolution milestone (`gcrts/cdrom_driver_map.py`,
  `XA_STREAM_RESOLUTION.md`'s own follow-up section) found the real
  low-level CD-ROM driver, live-hardware-verified, but not the live
  channel value itself.** A hardware write watchpoint on the CD-ROM
  controller's MMIO block (`0x1F801800`-`0x1F801803`) caught real writes
  from this game's own RAM code within seconds; the pointer-variable
  table those writes go through (`0x800A30BC`/`C0`/`C4`/`C8`) matches the
  real hardware register map exactly, live-verified end-to-end through
  `RuntimeSnapshot.cdrom_driver`. The shared command-issuing routine was
  located (`0x80081C00`) and the real Setfilter command number (`0x0D`,
  2 params: file, channel) confirmed against public documentation. This
  also explains, architecturally, why earlier filename-consumer scans
  found nothing: this game loads hardware pointers once into small RAM
  variables rather than constructing addresses inline, invisible to an
  address-construction scan. Separately, `0x800A61B0` (previously
  unidentified) is confirmed to be a real BIOS event descriptor, and its
  third dispatch branch was ruled out as PS1 Timer setup, not audio.
  **Three live attempts to catch the command routine actually firing
  with `0x0D` found zero hits** — a real, narrower blocker than before
  (mechanism and protocol known; one live observation still missing).
  `xa_channel` remains `POSITIONAL_UNCONFIRMED`.
- **Audio Captions milestone (`gcrts/audio_caption.py`) added a "what is
  being heard" layer, kept strictly separate from source/context
  identity.** Honestly limited to exactly one self-produced caption
  source: real, already-decoded dialogue text for confirmed
  `sound_or_voice_cue` events (`CaptionSource.SCRIPT_CONTEXT`,
  `CaptionConfidence.CONFIRMED`). This environment has no audio
  playback/listening capability and no classifier integrated, so no
  sound-effect/ambient descriptions are fabricated for real events —
  `MANUAL_LISTENING`/`USER_DEFINED`/`MODEL_INFERRED` sources are modeled
  for future use but never self-invoked with invented text.
- **`0x800A61AC`'s mechanism is now explained**: it advances because the
  confirmed dispatch site calls `0x80080d54` repeatedly (~6x/second)
  while a cue is active, each call overwriting it with a freshly
  computed, slightly larger LBA — not a separate incrementing counter.
  Its exact real-time UNIT (why the climb rate doesn't cleanly match a
  simple sectors/sec conversion) is still not confirmed;
  `playback_offset_ms` remains deliberately derived from wall-clock
  polling time, not this counter's scale — confirmed to be the correct
  design choice, not a stopgap.
- **`xa_channel` resolution is real but honestly downgraded**: confirmed,
  across 45 real sector reads, to be an EXACT positional artifact of the
  disc's own 8-way interleave (`channel_number == (lba - file_start) %
  8`, to the byte) — not independently proven to reflect the actual SPU
  playback channel. Reported under a dedicated
  `AudioConfidence.POSITIONAL_UNCONFIRMED` tier rather than silently
  presented with the same confidence as file resolution.
  `gcrts.cdrom_setfilter.KNOWN_SETFILTER_OBSERVATIONS` records a real,
  reproduced Setfilter call (`file=2, channel=1`), caught by fixing a
  real bug (a wrong stack offset) that three earlier live sessions had
  silently masked as "channel unreachable." **A follow-up simultaneous
  LBA/state cross-check (Audio Event Isolation milestone,
  `AUDIO_EVENT_EXTRACTION.md`) found this Setfilter is NOT proven to be
  event-specific** — it fired during a STOPPED state with a stale,
  unrelated `last_req_params`, twice independently, most likely a fixed
  default/reset value. A rigorous MATCH/MISMATCH comparison against the
  positional heuristic for a specific playing event therefore still
  isn't possible from this evidence — the positional heuristic remains
  the only value reported for any given live event's `xa_channel`.
  A read-only extraction backend (`gcrts.audio_event_extraction`) was
  built and tested regardless, deliberately never defaulting
  file/channel from this observation.
- 101 new tests across all eight milestones (25 lifecycle + 13 resolution
  + 14 script association + 16 audio context (incl. cross-validation)
  + 10 audio captions + net changes to existing tests), full suite
  478 passed.
- A small live map of the sound system's working-memory state exists:
  `0x800a6106`/`0x800a6107` (state pair, see above), `0x800a6114`-
  `0x800a6117` (confirmed last-requested raw parameters),
  `0x800a61a8`/`0x800a61ac`/`0x800a61b0` (structure/result pointers),
  `0x800a61b4` (tick counter), `0x800a61b8` (bitfield flags).
- No audio-inspector UI beyond the new minimal read-only panel exists
  yet (no waveform view, no extraction tool) — explicitly out of scope
  for this milestone, and still gated behind the movie-detection work
  per the project's own dependency order (runtime ID → movies → audio →
  subtitles) for anything beyond this one already-traced voice cue.
- `PROGHEAD.CDB`'s custom audio-bank format (`"BAV\x06"` magic, not
  standard Sony VAB) has a confirmed 16-byte record layout
  (`[index][u16 value][const=0x3c][const=0x40][8x 0xFF sentinel]`,
  cross-confirmed two independent ways). The `value` field is `0x7f`
  (the standard MIDI/PS1 max-value convention) in most records —
  plausibly per-program volume, not live-verified. Whether
  `PROGVAB.CDB` holds the sample data these records point to is
  unconfirmed.

### Subtitles — UNSUPPORTED (not started)

No implementation, no investigation started. Explicitly blocked on
Stage B (movie detection) and Stage C (audio source resolution —
partially done, see above) both producing stable, addressable event
IDs before a subtitle cue can reference "at this point in this movie."
`RuntimeSnapshot` already carries always-empty placeholder fields for
this, added deliberately ahead of time per the project's own workflow
instructions, not as a sign of partial implementation.

### Persistent build (disc-level, non-temporary edits) — LIVE_VERIFIED (PCSX-Redux only)

- A real disc-level edit (`gcrts`'s existing exact-size re-encoding
  pipeline) was written directly into a full copy of the real disc
  image at its actual ISO9660 LBA, respecting MODE2/2352 sector framing,
  with deliberately stale EDC/ECC. Verified byte-exact via read-back
  through `gcrts.iso9660`.
- **Live-verified surviving a completely fresh, non-instrumented
  PCSX-Redux boot** (no save state) — the edited label rendered
  correctly in actual gameplay after a real ~15-minute intro sequence
  and manual controller input. The original `game.bin` was never
  modified; only a copy was edited.
- **Scope limit**: proven in PCSX-Redux emulation only. This has not
  been validated as equivalent to a real-hardware-safe disc rebuild
  (no physical burn/hardware test, no independent EDC/ECC
  recomputation path built) — treat "persistent" here as "survives a
  fresh software emulator boot," not "verified real-hardware-safe."

---

## Capability matrix

| Subsystem | Current Status | Automatic? | Main Missing Piece |
|---|---|---|---|
| Repo / tests | LIVE_VERIFIED | Yes (`pytest`) | — |
| Disc / ISO9660 / CDB container | LIVE_VERIFIED | Yes | — |
| Compression (`cdb_codec`) | LIVE_VERIFIED | Yes | — |
| TIM (4/8/16bpp) | IMPLEMENTED | Yes | 24bpp unsupported |
| MENUDAT | IMPLEMENTED | Yes | Selected-state color mechanism unknown |
| PROGDAT | IMPLEMENTED | Yes | No dedicated composite-editing UI |
| SDB2.0 | PARTIAL | No | Outer directory-table addressing unsolved; no decode/edit |
| SDB2.2 / MS4 / GP4 | UNKNOWN | No | Not located in any real file yet |
| Asset Inspector | IMPLEMENTED | Partial (CLI+GUI) | No pixel-editor/undo stack |
| Runtime Asset Tracker | LIVE_VERIFIED | Yes | Profile coverage limited to validated executables |
| VRAM/GPU correlation | LIVE_VERIFIED | Yes (for `PROG.EXE`) | `PROG.EXE`'s own primitive-submission mechanism unidentified |
| Visual Inspector | LIVE_VERIFIED | Yes (750ms poll) | Combined-frame case unprovable on real game data (never co-occurs) |
| Global Selection | LIVE_VERIFIED | Yes | — |
| Runtime Snapshots | LIVE_VERIFIED | Manual trigger (Save/Load/Diff buttons) | `active_movie` always empty (by design, pending Movies); `active_audio` now real for the one confirmed cue |
| User Pages/Scenes | LIVE_VERIFIED | Manual creation, automatic re-matching | — |
| Renderer 1 | LIVE_VERIFIED core / IMPLEMENTED driver | Partial (needs external trigger) | Profile coverage: 1 of 15 executables |
| Renderer 2 | BLOCKED | No | Full trace never reproduced after 1 hit |
| CLD1 / layout descriptor | IMPLEMENTED | Yes (via Renderer 1 driver) | — |
| Script / font pipeline | LIVE_VERIFIED | Yes (external toolkit, verified) | Not yet merged into `gcrts` proper |
| Movies / `.STR` | PARTIAL | No | Runtime trigger unidentified; wrong overlay assumed so far |
| Audio / XA / voice | PARTIAL | Yes (`RuntimeSnapshot.active_audio` incl. nested `script_context`/`audio_context`/`caption`/`stream_source`/`extraction_status` + top-level `cdrom_driver`/`last_known_setfilter`, via `RuntimeVisualProvider`) | how the resolved filename becomes an actual file read not traced; a real Setfilter(file=2,channel=1) call is live-captured and reproduced but confirmed NOT proven event-specific (likely a default/reset value); a tested extraction backend (`gcrts.audio_event_extraction`) exists but has never run against a real confirmed event; event_end_lba unresolved; position counter's real-time unit uncalibrated; captions limited to dialogue text only; a real, live-firing `CD_init` function (sets the documented SPUCNT "CD Audio Enable" bit, `gcrts.spu_audio_path`) has been decisively ruled out, via a real user-confirmed audible correlation experiment, as the mechanism for that instance — as have both known Key ON/OFF site families; GDB's own SPU hardware register read/write path is confirmed unreliable, but PCSX-Redux's own native SPU debugger (`gcrts.pcsx_spu_observer`) is validated as a working replacement channel and shows CD Audio Enable genuinely, persistently set on real hardware (reversing the earlier "write does not persist" finding); a manual all-voices-muted experiment (native SPU Debug's per-channel Mute controls) found dialogue audio survives every regular SPU voice being muted, reproduced in two independent scenes (`gcrts.spu_audio_path.all_spu_voices_muted_dialogue_still_audible()` → `True`) — the audio bypasses the SPU's 24-voice mixing engine entirely and enters via the CD input path; `classify_playback_backend()` now returns `CD_INPUT_UNKNOWN_FORMAT` (not `XA_ADPCM_CONFIRMED` — that specific stream format was not independently re-verified); a virtual XInput gamepad (vgamepad/ViGEmBus) was validated at the Windows/XInput level but never got the game itself to respond, so automated dialogue-triggering remains unreliable and further live-correlation work still needs a human trigger |
| Subtitles | UNSUPPORTED | No | Not started; blocked on Movies + Audio |
| Persistent build | LIVE_VERIFIED (emulator only) | No (manual disc-copy step) | Not validated for real hardware |
