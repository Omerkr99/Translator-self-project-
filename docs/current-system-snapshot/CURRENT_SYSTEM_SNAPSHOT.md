# Current System Snapshot

Snapshot date: 2026-08-10 (Asia/Jerusalem)

## Current State

GCRTS is currently a specialized reverse-engineering and translation toolkit for the PlayStation game *Twilight Syndrome: Tansaku Hen*. It is not yet one integrated end-user translation application. Its most complete visible workflow is raster asset inspection/editing, backed by exact-size rebuilding and temporary PCSX-Redux patching. A second desktop tool maps visible screen regions to their source assets and can correlate a running emulator's RAM, VRAM, and GPU ordering-table data.

Dialogue translation is substantially implemented behind a terminal workbench and Python services: live script-buffer capture, decode/edit/validate/re-encode/inject, glyph auditing, text fitting, layout plans, session persistence, and guarded injection. That workflow is not exposed through the desktop inspectors. Only dialogue has a real live text render-path adapter; menu/system/status/chapter text adapters remain explicit stubs. Raster menu labels are editable separately as image assets.

Evidence used for this snapshot:

- Direct launch and interaction with both Tk desktop inspectors.
- A live PCSX-Redux session available at the local HTTP API. A scan returned three exact correlations: `Start`, `Prepare`, and `Classroom Background`, all `DRAWN_THIS_FRAME` with `LIVE_EXACT_VRAM_GPU` evidence.
- The repository's real `MENUDAT.BIN` and `PROGDAT.BIN`, not generated demo data.
- The repository's asset CLI, which decoded and listed all 32 MENUDAT assets.
- `python -m pytest -q tests`: **368 passed**, six Pillow deprecation warnings, in 15.78 seconds. Running bare `pytest` first failed during collection because repository-root artifact directories were inaccessible; scoping collection to `tests/` succeeded.
- Direct source inspection. Documentation was treated as supporting context, not proof.

No application source was changed. Screenshot automation instantiated the existing windows, positioned them in the foreground, and used Pillow `ImageGrab`; no automation hook was added. Running the existing UI may update its normal file-backed cross-window selection (`project_selection.json`), and the runtime page detector can persist observations to `runtime_pages.json`; no manual edits were made to either file.

## Working Features

### Desktop Asset Inspector — VERIFIED LIVE

- Opens the real compressed MENUDAT/PROGDAT containers and displays decoded TIM assets in a searchable thumbnail browser.
- Shows source path, block, compressed offset/size, decoded size, dimensions, pixel format, palette, semantic status, editing capabilities, and descriptor validation.
- Displays and inspects 4bpp indexed Japanese raster labels and their 16-entry CLUTs.
- Shows live `[DRAWN]` badges when the running-emulator correlation identifies an asset in the current frame.
- Exports a selected asset to PNG and accepts palette-preserving replacement PNGs. Invalid dimensions or colors are rejected by the backend.
- Applies an indexed text overlay with X/Y/palette-index controls and optional clearing of existing pixels.
- Computes the recompressed size before output. The observed Start asset reported `508 / 514`, with safe exact-size padding to 514 bytes.
- Rebuilds an edited container without changing unrelated blocks and records output through the asset workspace.
- Temporarily patches the corresponding disc file in PCSX-Redux and can restore in-memory edits.
- Treats five 64x240 PROGDAT strips as one 320x240 composite image for export/replacement while preserving independent palettes and size budgets.

The PNG export, replacement, overlay, build, exact-size safety, composite round-trip, and workspace paths are additionally covered by passing tests. I did not deliberately write a new translated output or inject a changed asset during this baseline capture, because the task forbids changing behavior/state beyond evidence collection.

### Visual Inspector — VERIFIED LIVE

- Loads a screenshot or captures the current 320x240 screen from PCSX-Redux VRAM.
- Displays registered object bounds and metadata for main menu, system menu, and spoils/photo contexts.
- Filters by translation relevance, assets, Renderer 1, Renderer 2, and unknown regions.
- Selects an object, shows source/provenance, text representation, translation status, confidence, screen bounds, editor route, and route availability.
- Routes editable raster assets to the Asset Inspector.
- Supports a manual mapping mode and persisted mapping registry; live-verified mappings are protected from deletion.
- Shares selected asset state between separate tool windows using `project_selection.json`.
- With a live emulator, scans RAM and VRAM, parses GPU ordering-table primitives, fingerprints assets, correlates texture uploads/draws, and replaces static objects with current-frame objects.
- The verified live scan detected Start at approximately `(60,200,100,24)`, Prepare at `(160,200,100,23)`, and the classroom background at `(0,0,320,240)`.
- Tracks runtime lifecycle/provenance (`LOADED`, `UPLOADED_TO_VRAM`, `DRAWN_THIS_FRAME`, stale/overwrite/unload states) and discovers runtime pages from observed asset sets.

### Generic binary text extraction — VERIFIED LIVE

- CLI loads a binary, detects printable ASCII, Shift-JIS, and simple ASCII-range UTF-16LE runs, clusters nearby strings, and writes JSON with offsets and metadata.
- Detection and clustering are covered by passing tests. The detector is heuristic and is not the game's custom dialogue decoder.

### Live dialogue workbench — VERIFIED IN CODE

- Terminal UI can capture the known live dialogue script buffer through the GDB remote protocol, decode it into bounded script units, display Japanese original and editable text, preserve raw codes/control events, search/filter, annotate, and persist sessions.
- Supports edit/reset, automated validation, operator-confirmed overflow status, boundary and chain checks, injection history, and whole-buffer live reinjection.
- Guarded single-unit injection blocks missing-glyph/control failures and logs attempts, while internally writing the whole buffer to preserve offsets.
- Dialogue is the only implemented live text-type adapter.
- Core operations have passing unit/integration-style tests, but I did not alter or reinject dialogue in the running game during this snapshot, so this is not marked VERIFIED LIVE here.

### Encoding, controls, fitting, fonts, and layout — VERIFIED IN CODE / PARTIAL

- Custom script decode/encode round-trips known characters, control events, and unknown-code placeholders.
- Control-code index/policy and positional-risk analysis exist.
- Text fitting supports calibrated character widths, optional real glyph measurements, engine-aware wrapping, forced-wrap controls, padding, and centering.
- Glyph workbench classifies mapped/substitutable/unmapped characters, applies known substitutions, audits coverage, and can inject a new glyph into a live unused scene slot with an audit log.
- Layout validation reports missing glyphs, control issues, boundary risk, pixel overflow, line-count problems, awkward wrapping, or OK.
- Editable layout plans support original/host-fitted/custom-engine modes, line position/alignment/style editing, textual preview, and software-rendered PNG preview.
- A compact `CLD1` descriptor codec, descriptor injection, Renderer 1 profile validation, active-record snapshots, per-character positioning, reversible live coordinate overrides, and rollback/readback safety exist.
- **PARTIAL:** `CUSTOM_ENGINE` records intent and creates descriptors/previews, but no in-game custom renderer consumes it. The terminal help explicitly states that live injection remains host-fitted-equivalent.
- **PARTIAL:** new glyph live injection exists, but persistent font-file rebuilding is blocked because the exact font compressor is not implemented.

### Disc/container and patch safety — VERIFIED IN CODE

- ISO9660 lookup and CD sector handling exist.
- CDB/script codecs, asset stream decompression/recompression, TIM parsing/encoding, fingerprints, descriptors, and exact-size policies are separated into reusable services.
- Live memory/disc injection paths use validation, checksums/readback, rollback, or temporary emulator patch APIs rather than silently overwriting a source image.

## Current User Workflow

There is no launcher or project dashboard. A user must know which Python module and file arguments to run.

The usable raster-asset path today is:

1. Start PCSX-Redux separately if live capture, current-frame badges, or temporary patch testing is wanted.
2. Launch `python -m gcrts.visual_inspector_ui`, optionally with a known context, screenshot, or capture flag.
3. Capture/load a screen, inspect mapped regions, toggle Translation View, and select a known raster asset.
4. Use **Open Correct Inspector** to launch the Asset Inspector for that block/composite, or launch `python -m gcrts.asset_inspector_ui <source>` directly.
5. Browse/search decoded Japanese raster labels or composite backgrounds; inspect palette, dimensions, source, and byte budget.
6. Apply a simple indexed overlay or replace with a same-size, palette-compatible PNG.
7. Confirm the compressed budget remains safe, build a modified container, and optionally temporarily patch it into PCSX-Redux.
8. Reset/reload the emulator to see the patch, then restore the in-memory edit or clear patches through the CLI.

The dialogue path is separate and developer-oriented:

1. Start the game/emulator and GDB endpoint at the expected scene/buffer state.
2. Launch `python -m gcrts.editor_cli --extract <scene_id>`.
3. List/show units, edit English text, resolve/audit glyphs, fit text, validate layout and boundaries, preview plans, then guarded-inject and visually confirm the result in-game.
4. Save the JSON workbench session and glyph log as needed.

There is no UI that ties disc/game selection, script extraction, Japanese/English editing, font work, visual preview, injection, and final image creation into one guided project workflow.

## Visual Evidence

- [`screenshots/01-asset-inspector-main-menu-start.png`](screenshots/01-asset-inspector-main-menu-start.png) — Real MENUDAT catalog with Japanese raster labels, Start selected, source/offset/format/capabilities, 16-color CLUT, overlay controls, live `[DRAWN]` badges, and an exact compressed-size budget.
- [`screenshots/02-asset-inspector-classroom-composite.png`](screenshots/02-asset-inspector-classroom-composite.png) — Five real PROGDAT strips assembled into the logical 320x240 classroom background, with composite provenance and editing constraints.
- [`screenshots/03-asset-inspector-prepare-text.png`](screenshots/03-asset-inspector-prepare-text.png) — A second genuine Japanese UI-text asset (`Prepare / Settings`) and its independent palette/budget state.
- [`screenshots/04-visual-inspector-main-menu-mappings.png`](screenshots/04-visual-inspector-main-menu-mappings.png) — Static/manual-fallback mapping view over the extracted classroom screen: background, Start, Prepare, and an explicitly unknown region; the side panel demonstrates source-to-editor routing.
- [`screenshots/05-visual-inspector-translation-view.png`](screenshots/05-visual-inspector-translation-view.png) — Translation View filtering the screen model to text-relevant raster assets.
- [`screenshots/06-live-pcsx-vram-capture.png`](screenshots/06-live-pcsx-vram-capture.png) — Raw 320x240 frame captured from the running PCSX-Redux VRAM API during this audit.
- [`screenshots/07-visual-inspector-live-runtime-tracking.png`](screenshots/07-visual-inspector-live-runtime-tracking.png) — Strongest runtime proof: the inspector populated from live RAM/VRAM/GPU correlations, with current snapshot/page status and selected Start provenance.
- [`screenshots/08-actual-start-translation-built.png`](screenshots/08-actual-start-translation-built.png) — A real edit rather than a mock-up: block 7's Japanese `開始` pixels were cleared and replaced with `START` through `AssetProject.text_overlay`. The inspector displays the changed decoded TIM and a safe exact-size rebuild (`203 / 514` compressed bytes, padded back to 514).
- [`screenshots/09-live-emulator-translated-start.png`](screenshots/09-live-emulator-translated-start.png) — The translated `START` texture visibly rendered inside the running PCSX-Redux window at the original Japanese label's position. After loading the repository's title/main-menu save state, the system found `main_menu.start` at live VRAM `(896,48)`, replaced its 25x24-word indexed texture region through the emulator API (`HTTP 200`), and captured the actual emulator window. This is live runtime evidence, not an external composite.

The corresponding rebuilt container is [`generated-evidence/MENUDAT-START-translated.BIN`](generated-evidence/MENUDAT-START-translated.BIN), SHA-256 `67FC2751FEA6E4A0EE381A6EA3E951E4305728C7664B9C656790AE002CC5F59B`. It is a separate output artifact; the source `sdb_main_menu_asset/MENUDAT.BIN` was not overwritten and the temporary emulator patch was not changed.

## Hidden / Developer-Only Capabilities

- Terminal-only live Japanese/English dialogue editing and session management.
- Generic binary text extraction/clustering JSON CLI.
- Asset automation CLI for list/show/export/text/build and emulator patch clearing.
- Runtime scanning CLIs and a Lua runtime probe/event feed.
- Custom script decoder/encoder, unknown-code preservation, control-code index, and control-position risk reports.
- Layout planning, CLD1 descriptor serialization, software preview rendering, runtime profile validation, and reversible coordinate overrides.
- Font atlas inspection, glyph classification/substitution, live glyph-slot injection, and glyph audit logs.
- ISO9660/CD-ROM parsing and safe patch helpers.
- GPU ordering-table parsing, VRAM asset fingerprint detection, draw correlation, lifecycle history, runtime page detection, and cross-window selection.
- MIPS JAL decoding and named patch/profile validation systems.

These systems are real modules with test coverage, but most require direct Python/CLI use and knowledge of fixed emulator endpoints, addresses, files, or profiles.

## Current Limitations

- No integrated home screen, project/game loader, setup diagnostics, or guided workflow.
- No desktop script extraction/translation editor; the only Japanese/English unit view is terminal text.
- Only the dialogue live render path is implemented. `speaker_label` (independent path), `menu`, `system_prompt`, `status_overlay`, and `chapter_title` are explicit `NotImplementedError` adapters. Raster menu labels are a separate asset-editing path.
- No complete custom in-game text renderer. Custom layout plans and CLD1 descriptors are producer-side infrastructure without a runtime consumer.
- No final disc-image build/repack workflow exposed to users. Asset output is a rebuilt container; testing uses temporary PCSX-Redux patches.
- Live features depend on separately running PCSX-Redux/GDB services and highly game/version-specific files, addresses, and profile validation.
- The Visual Inspector can open the Asset Inspector, but text-layout routes surface only an informational dialog; Renderer 2 is investigation-only and not editable.
- Static mapping coverage is narrow (three named contexts) and still includes unknown regions.
- Generic extraction is heuristic and does not classify all content types; font glyph-table and UI border/box detection are explicitly absent from that detector.
- TIM 24bpp direct color is not implemented; the current known assets are indexed formats.
- Font extension is live/temporary; the exact persistent font compressor is missing.
- Some pixel-accurate commands assume an external `C:/PCSXRedux/CAP0_full.bin` and a specific Windows font path.
- Runtime tracking errors are reduced to a status line or empty badges, with no user-facing connection/setup recovery flow.
- Bare repository-root pytest collection is currently noisy/broken on inaccessible artifact directories; `pytest tests` passes.

## Important Architecture Already Present

- Backend-first separation: Tk and terminal UIs call service modules instead of embedding binary logic.
- `AssetDescriptor`/registry/fingerprint model: canonical identity, source provenance, encoding policy, semantics, capabilities, and validation.
- `AssetProject`: reversible in-memory edits, palette-preserving indexed import, composite member handling, exact-size recompression, and unchanged-block preservation.
- `ScriptUnit` + `EditorState`: bounded editable units, original/edited text, controls, validation, layout plan, notes, history, and session persistence.
- Adapter registry for multiple text render paths, honest about unimplemented families.
- Validation/safety layers: control preservation, glyph coverage, boundaries, layout, checksums, readback, rollback, stale-profile rejection, and temporary patching.
- Screen-object/mapping/dispatch model connecting visible coordinates to assets, renderers, source evidence, and the correct editor target.
- Runtime evidence pipeline: emulator capture -> RAM/VRAM -> ordering table -> asset detection/correlation -> lifecycle tracker -> current screen objects/page discovery.
- Renderer 1 profile and CLD1 descriptor abstractions, which are useful foundations even though the custom runtime consumer is unfinished.

These are the systems future work should integrate and expose, not rebuild from scratch.
