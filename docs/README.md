# Documentation Index

Every markdown doc in this project (other than the root `README.md`)
lives under one of these categories. This index exists so any file can
be found by topic instead of scrolling a flat list of ~60 files.

**Start here for "what actually works right now"**:
[`status/CURRENT_SYSTEM_STATUS.md`](status/CURRENT_SYSTEM_STATUS.md) —
the single, continuously-updated "present truth" document: test counts,
capability matrix, and what's live-verified vs. still open.

**Resuming the audio/SPU investigation specifically?** Start at
[`audio/AUDIO_INVESTIGATION_RESUME.md`](audio/AUDIO_INVESTIGATION_RESUME.md)
instead of the full chain below — it's a single "pick up here" page
with the current state, environment setup steps, and the exact next
task.

## Categories

### [`audio/`](audio/) — the XA/voice audio investigation chain
Script cue → selector → XAPACK file → event/stream descriptor → real
CD-ROM driver → live-captured Setfilter call → read-only extraction
backend. Read in this order for the full story: `RUNTIME_AUDIO_TRACKER.md`
(lifecycle) → `AUDIO_CUE_RESOLUTION.md` (source resolution) →
`SCRIPT_AUDIO_ASSOCIATION.md` (which script line owns which audio) →
`AUDIO_CONTEXT_RESOLUTION.md` (why that line picks its source) →
`XA_STREAM_RESOLUTION.md` (file-open, CD-ROM driver, and the real
Setfilter capture) → `AUDIO_CAPTIONS.md` (what is being heard) →
`AUDIO_EVENT_EXTRACTION.md` (the extraction backend, and the "Setfilter
not proven event-specific" correction) → `CDROM_SETFILTER_CAPTURE.md`
(the live session that found the filter looks persistent, not per-cue)
→ `AUDIO_PLAYBACK_TRUTH.md` (why `0x800A6107` is not audible-playback
truth, and the still-open search for the real signal) →
`XA_PLAYBACK_PATH.md` (CD-DA structurally ruled out via the real disc's
own `.cue` file; the real XA path still open) →
`CDROM_DRIVER_DISCOVERY.md` (a full RAM value scan found 7 additional
CD-ROM register pointer sets, identified as interrupt/DMA
infrastructure, not a second audio driver) →
`SPU_AUDIO_PATH_DISCOVERY.md` (pivoted to the SPU side; found a real,
live-firing `CD_init` function that sets the documented "CD Audio
Enable" SPUCNT bit, then decisively ruled it and known Key ON/OFF
sites out via a real user-confirmed audible correlation experiment) →
`SPU_OBSERVATION_CHANNEL.md` (found PCSX-Redux's own native SPU
debugger, proving GDB's SPU register reads were simply wrong — CD
Audio Enable is genuinely, persistently set on real hardware; also
found a real crash-loop bug and confirmed synthetic keyboard input
doesn't reach the game) → `AUDIO_TRANSPORT_PATH.md` (a manual
all-voices-muted experiment proved dialogue bypasses all 24 SPU
voices; a DMA investigation via PCSX-Redux's native HW Registers
window then found zero CD-ROM/SPU DMA activity during a confirmed
voice line, pointing to a direct hardware audio bus bypassing system
DMA — transport and stream format are now modeled as separate
concepts; a follow-up pass then confirmed SPU-internal RAM inspection
is a genuine tooling blocker across GUI/Lua/GDB, and ruled out the SPU
Debug window's own live XA panel as a dialogue-correlated signal via
two precisely-timed live captures) → `XAPACK_FORMAT.md` (worked
offline instead: a byte-level scan of every audio sector across all 43
real XAPACK files found standard Green Book CD-XA real-time-audio
sectors with `coding_info=0x01`, finally resolving `classify_stream_
format()` to `XA_ADPCM`; also found a real per-channel EOF marker
solving event segmentation, and built a raw+decoded-WAV extraction
pipeline) → `AUDIO_ASSET_MODEL.md` (the resulting `AudioAsset` identity
model and `ScriptAudioAssociation → AudioAsset` runtime bridge) →
`XA_DECODER_VERIFICATION.md` (diffed the decoder against FFmpeg's
independent `adpcm_xa` decoder, found and fixed two real layout bugs
plus a mono-handling bug, reached 100.0000% exact sample match on 5
real assets — `REFERENCE_VERIFIED`) →
`SEMANTIC_AUDIO_CLASSIFICATION.md` (a fourth layer — physical format
says nothing about semantic role; relative within-pack feature
classification plus human-in-the-loop confirmed-label persistence and
a per-pack review-folder pipeline, `review.html` included; caught and
fixed a real classifier bug — regular loops vs. genuinely irregular
speech bursts — against the one already-confirmed asset) →
`FANDUB_REPLACEMENT_TEMPLATE.md` (the product-access layer's first
piece — a translation/dub template + rules-only validation preview,
gated on a confirmed semantic label, no injection/encoding
implemented) →
`DIALOGUE_DATABASE.md` (the unified per-asset workbench record —
combines physical identity, confirmed semantic label, and Fandub
template into one `DialogueDatabaseEntry` with a derived, never-jumps-
ahead workflow status) →
`LIVE_AUDIO_INSPECTOR.md` (wraps the LBA resolver + Dialogue Database
into a live `NOW PLAYING: <asset_id>` panel in the Visual Inspector;
never overwrites an existing entry's hand-added evidence; live-verified
against the actually-running emulator) →
`SUBTITLE_EXPORT.md` (the first product-access deliverable, text-only
subtitles before dubbing — a real `.srt` for the confirmed save-slot-9
voice line, plus a real speaker-prefix duplication bug caught and fixed
at the source) →
**retraction (2026-08-23)**: 5 fresh live candidates for the
save-slot-9 line were all rejected on listening, including the
previously-confirmed `XAPACK22:7` — downgraded to `UNVERIFIED`,
evidence preserved, not deleted →
`SPU_PLAYBACK_TRACE.md` (the methodology shift this forced:
playback-first, not CD-first, identification — a structured SPU
Key-write/heartbeat/marker trace schema, a PCSX-Redux Lua tracer
verified against the emulator's real FFI source, and a classifier
naming `SPU_VOICE_PLAYBACK`/`CD_AUDIO_INPUT`/`OTHER_OR_UNKNOWN` with
cited evidence) → the live run found `CAP0.EXE` (not `PROG.EXE`) is
the executable actually resident during the save-slot-9 scene — real
signatures for every overlay executable now live in `gcrts.overlay_
identity` — but the trace itself kept stopping early regardless of
what was changed, with `GPU::Vsync` proven to keep firing throughout →
`AUDIO_DATA_TRACE.md` (the resulting pivot: control-flow tracing →
data tracing — offline RAM-snapshot diffing, multi-signal candidate
scoring, format heuristics, and a real, validated audio fingerprint
matcher against the existing `AudioAsset` catalog) → five more internal
angles each pursued to a real, disciplined negative (CD command/DMA/SPU
MMIO tracing, a full-coverage static CD Data FIFO scanner
`gcrts.cdrom_fifo_scanner`, and a statistical PC-sampling runtime
profiler after 890 simultaneous breakpoints were found to slow the
interpreter to a crawl) → `OUTPUT_AUDIO_CAPTURE.md` (the pivot that
resolved it: WASAPI loopback capture of the emulator's real digital
output, `gcrts.output_audio_capture`, localized by the waveform's own
acoustic shape, matched via a sliding-window offset-continuity search —
`XAPACK22:7` reconfirmed `USER_LISTENING` after its earlier retraction,
independently, by a completely different method) →
`AUDIO_INVESTIGATION_RESUME.md` (the actionable "pick up here" page for
the next session).

### [`assets/`](assets/) — image/sprite asset pipeline
Decoding, cataloging, safely re-injecting, and inspecting TIM/MENUDAT-
style visual assets: `ASSET_DESCRIPTOR_SPEC.md`, `ASSET_INJECTION_SAFETY.md`,
`ASSET_INSPECTOR_ARCHITECTURE.md`, `CUSTOM_LAYOUT_DESCRIPTOR.md`,
`IMAGE_ASSET_STATUS.md`, `IMAGE_FORMAT_ADAPTERS.md`,
`MENUDAT_ASSET_CATALOG.md`, `SDB_MAIN_MENU_ASSET_REPORT.md`,
`VISUAL_ASSET_INSPECTOR.md`.

### [`renderer/`](renderer/) — GPU/VRAM rendering pipeline
How assets and text actually reach the screen via ordering tables and
GPU primitives: `FRAME_RENDER_MODES.md`, `GPU_ASSET_CORRELATION.md`,
`GPU_OT_RUNTIME_MAP.md`, `INDIRECT_RENDER_TARGETS.md`,
`MASTER_RENDER_MODE_MAP.md`, `MODE3_TRIGGER_INVESTIGATION.md`,
`RENDERER_1_RUNTIME_DRIVER.md`, `RENDERER_ASSET_INTEGRATION.md`,
`RENDERER_LIVE_PROOF.md`, `RENDERER_SYSTEM_STATUS.md`,
`VRAM_PROVENANCE_TRACKING.md` → `MOVIE_DETECTION.md` (resolved the
long-blocked movie-runtime-detection question by reusing
`gcrts.overlay_identity`'s movie-player family directly — no DMA
tracing needed — live-confirmed against a real `OP.STR` playthrough;
wired into `RuntimeSnapshot.active_movie`) → `MOVIE_LOADER_ARCHITECTURE.md`
(maps which chapter executable selects which movie and how, via a
reusable MIPS disassembler + scanner — `gcrts.mips_disasm` /
`gcrts.movie_loader_scan` — including a wrong hand-off hypothesis this
same investigation made and then disproved with a live breakpoint
test).

### [`text-engine/`](text-engine/) — dialogue text, script decoding, translation
The alternative text engine investigation, script bytecode, and where
dialogue text actually comes from on screen: `TEXT_ENGINE_ARCHITECTURE.md`,
`TEXT_POSITION_SOURCE_PLAN.md`, `TEXT_POSITION_TRACE_LOG.md`,
`TRANSLATION_VIEW.md`, `DECODER_READ_CURSOR.md`, `SCRIPT_CONTROL_INDEX.md`,
`DIALOGUE_GPU_PACKET_MAP.md`, `VISIBLE_DIALOGUE_COMPOSITION_PATH.md`,
`MIPS_PATCH_PLAN.md`, `MEMORY_MAP_FINDINGS.md`, `BASELINE_REPORT.md`.

### [`runtime/`](runtime/) — live runtime tracking infrastructure
The non-audio-specific runtime layer: asset lifecycle tracking, screen
object mapping, the Visual Inspector, snapshots, and user-defined pages:
`GLOBAL_SELECTION_MODEL.md`, `RUNTIME_ASSET_STATE_MACHINE.md`,
`RUNTIME_ASSET_TRACKER.md`, `RUNTIME_PAGE_DISCOVERY.md`,
`RUNTIME_SNAPSHOT.md`, `SCREEN_ASSET_MAPPING.md`,
`SCREEN_MAPPING_REGISTRY.md`, `SCREEN_OBJECT_MODEL.md`,
`VISUAL_INSPECTOR_ARCHITECTURE.md`, `USER_CONTROLLED_PAGES.md`.

### [`tooling/`](tooling/) — reusable methodology and infrastructure
How live captures are actually taken, and shared decoding tools:
`MIPS_JAL_DECODER.md`, `PCSX_REDUX_CAPTURE_PROTOCOL.md`,
`BREAKPOINT_GENERATION_LOG.md`, `PCSX_PAD_INPUT_BRIDGE.md` (the real,
working mechanism for programmatic PS1 controller input --
PCSX-Redux's own Lua-exposed hardware-level pad override, confirmed
against the real emulator source; bypasses window focus/OS input
entirely), `PCSX_KEYBOARD_INPUT.md` (superseded for controller input by
the above -- OS-level `SendInput` reliably drives PCSX-Redux's own UI
but not the emulated controller, a distinction this doc's own history
initially got wrong).

### [`overlay_engine/`](overlay_engine/) — external/internal overlay subsystem
The staged plan for a shared external (host-side, emulator-synchronized)
and internal (PS1-resident, patched-into-the-game) localization overlay:
`PS1_OVERLAY_RUNTIME_REQUIREMENTS.md` (SRS),
`PS1_OVERLAY_RUNTIME_SYSTEM_DESIGN.md` (SDD), and
`GROUNDING_ANALYSIS.md` — which maps every spec component against real
`gcrts` code, distinguishes what already existed
(`gcrts.gdb_client`/`overlay_identity`/`movie_detection`/`renderer1_runtime`,
all `CONFIRMED_LIVE`) from what's genuinely new
(`gcrts.evidence`, `gcrts.emulator_adapter`, `gcrts.pcsx_redux_adapter`,
`gcrts.runtime_context` — built and tested this session, Stage 1 of the
staged plan), and gives the concrete next stages.

### [`investigations/`](investigations/) — research logs and scoping
Point-in-time investigation records and planning documents:
`BACKLOG_INVESTIGATION_RESULTS.md`, `BACKLOG_INVESTIGATION_SCOPE.md`,
`EXPERIMENT_PLAN.md`, `DISC_FILE_CATALOG.md`.

### [`status/`](status/) — top-level project status and summaries
`CURRENT_SYSTEM_STATUS.md` (the canonical one — start there),
`TOOLKIT_READINESS_AUDIT.md` (a full evidence-based readiness audit
performed before any move toward a reusable, game-agnostic toolkit —
confirmed capabilities, partial/unknown items, disproven claims,
game-specific leakage, test-validation quality, and a go/no-go
decision). `GCRTS_CHANGES_SINCE_1200.md`, `GCRTS_COMPLETE_WORK_SUMMARY_HE.md`,
`GCRTS_FULL_SYSTEM_AUDIT.md`, `NOTES.md` are **dated, frozen snapshots**
from a single earlier day (2026-08-09), not current state — only
`CURRENT_SYSTEM_STATUS.md` and `TOOLKIT_READINESS_AUDIT.md` should be
treated as live.

### [`current-system-snapshot/`](current-system-snapshot/) — generated evidence snapshot
A separately-maintained generated snapshot (screenshots + evidence),
not part of the hand-written docs above.

## A note on cross-references

Docs written before this reorganization reference each other by bare
filename (e.g. `` `AUDIO_CONTEXT_RESOLUTION.md` ``), not full path —
none of them were formatted as clickable relative markdown links, so
moving files didn't break anything, but a mention won't tell you which
subfolder to look in. Use this index, or search by filename, to find
the current location.
