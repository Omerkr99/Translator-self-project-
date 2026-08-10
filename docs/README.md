# Documentation Index

Every markdown doc in this project (other than the root `README.md`)
lives under one of these categories. This index exists so any file can
be found by topic instead of scrolling a flat list of ~60 files.

**Start here for "what actually works right now"**:
[`status/CURRENT_SYSTEM_STATUS.md`](status/CURRENT_SYSTEM_STATUS.md) —
the single, continuously-updated "present truth" document: test counts,
capability matrix, and what's live-verified vs. still open.

## Categories

### [`audio/`](audio/) — the XA/voice audio investigation chain
Script cue → selector → XAPACK file → event/stream descriptor → real
CD-ROM driver → live-captured Setfilter call. Read in this order for
the full story: `RUNTIME_AUDIO_TRACKER.md` (lifecycle) →
`AUDIO_CUE_RESOLUTION.md` (source resolution) →
`SCRIPT_AUDIO_ASSOCIATION.md` (which script line owns which audio) →
`AUDIO_CONTEXT_RESOLUTION.md` (why that line picks its source) →
`XA_STREAM_RESOLUTION.md` (file-open, CD-ROM driver, and the real
Setfilter capture) → `AUDIO_CAPTIONS.md` (what is being heard).

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
`VRAM_PROVENANCE_TRACKING.md`.

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
`BREAKPOINT_GENERATION_LOG.md`.

### [`investigations/`](investigations/) — research logs and scoping
Point-in-time investigation records and planning documents:
`BACKLOG_INVESTIGATION_RESULTS.md`, `BACKLOG_INVESTIGATION_SCOPE.md`,
`EXPERIMENT_PLAN.md`, `DISC_FILE_CATALOG.md`.

### [`status/`](status/) — top-level project status and summaries
`CURRENT_SYSTEM_STATUS.md` (the canonical one — start there),
`GCRTS_CHANGES_SINCE_1200.md`, `GCRTS_COMPLETE_WORK_SUMMARY_HE.md`,
`GCRTS_FULL_SYSTEM_AUDIT.md`, `NOTES.md`.

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
