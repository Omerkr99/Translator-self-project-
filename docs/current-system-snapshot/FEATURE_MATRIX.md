# Feature Matrix

Verification labels reflect this 2026-08-10 snapshot. “Verified live” means exercised against the bundled real assets or the running PCSX-Redux session, not merely observed in documentation.

| Feature | Exists | UI exposed | Verified live | Maturity | Notes |
| ------- | ------ | ---------- | ------------- | -------- | ----- |
| Project/game launcher | No | No | No | NOT WORKING / NOT CONNECTED | Users launch individual Python modules with paths and flags. |
| Known game/context selection | Yes | Partial | Yes | PARTIAL | Visual Inspector has three registered contexts; no general project wizard. |
| Generic binary loading | Yes | CLI | Yes | WORKING | Loads a file as one binary segment. |
| ASCII text-run extraction | Yes | CLI | Tests/code | WORKING | Heuristic printable-run detection. |
| Shift-JIS text-run extraction | Yes | CLI | Tests/code | WORKING | Uses structural and kana heuristics to reduce false positives. |
| UTF-16LE text-run extraction | Yes | CLI | Tests/code | PARTIAL | Detects printable ASCII-range UTF-16LE pairs, not arbitrary Unicode. |
| Extracted-string clustering/JSON | Yes | CLI | Tests/code | WORKING | Groups nearby runs and emits offsets/metadata. |
| Content classification beyond text | Partial | No | No | PARTIAL | Loader does not split texture/font/UI/animation generally. |
| Game dialogue live extraction | Yes | Terminal | Tests/code | PARTIAL | One known live script buffer/GDB workflow; not exercised destructively in this audit. |
| Menu/system/status/chapter live text extraction | Stub | Terminal status | No | NOT WORKING | Explicit `NotImplementedError` adapters. |
| Independent speaker-label extraction | Stub | Terminal status | No | NOT WORKING | Speaker controls are decoded inside dialogue; separate path unknown. |
| Custom script decode | Yes | Terminal detail | Tests/code | WORKING | Produces bounded units, text, raw codes, and control events. |
| Custom script encode/round-trip | Yes | Terminal action | Tests/code | WORKING | Preserves supported controls and unknown placeholders. |
| Japanese original / English edited unit view | Yes | Terminal | Tests/code | PARTIAL | Detailed but not a desktop editing interface. |
| Search/filter/edit/reset/notes | Yes | Terminal | Tests/code | WORKING | Managed by reusable `EditorState`. |
| Translation session save/load | Yes | Terminal | Tests/code | WORKING | JSON persistence includes units and editing state. |
| Control-code index and policy | Yes | Terminal/backend | Tests/code | WORKING | Known meanings, preservation/drop decisions, and metadata. |
| Control-position risk analysis | Yes | Terminal/backend | Tests/code | WORKING | Accounts for forced-wrap/position-affecting events. |
| Boundary/chain validation | Yes | Terminal | Tests/code | WORKING | Detects size shifts and bookkeeping drift. |
| Text fitting/reflow | Yes | Terminal | Tests/code | WORKING | Engine-aware wrapping, optional centering and pixel measurement. |
| Automated layout validation | Yes | Terminal | Tests/code | WORKING | Glyph/control/boundary/overflow/line/wrap status ladder. |
| Operator in-game confirmation | Yes | Terminal | Tests/code | PARTIAL | Manual `ok`/`overflow` recording; no integrated visual comparison. |
| Guarded live dialogue injection | Yes | Terminal | Tests/code | PARTIAL | Safety-checked whole-buffer write; requires live GDB target. |
| Injection history | Yes | Terminal | Tests/code | WORKING | Persists attempt outcomes per unit. |
| Glyph map/coverage audit | Yes | Terminal/backend | Tests/code | WORKING | Classifies mapped, substitutable, and unmapped characters. |
| Known glyph substitution | Yes | Terminal | Tests/code | WORKING | Resolves known substitutions before fitting. |
| Live new-glyph injection | Yes | Terminal | Tests/code | PARTIAL | Temporary unused-slot injection with audit log; external atlas required. |
| Persistent font rebuild | No | No | No | NOT WORKING | Exact font compressor is explicitly missing. |
| Font/glyph visual desktop inspector | No | No | No | NOT CONNECTED | Font services exist without a dedicated GUI. |
| Editable layout plan | Yes | Terminal | Tests/code | PARTIAL | Line spans, X/Y, alignment, style, and render-mode intent. |
| Layout text preview | Yes | Terminal | Tests/code | WORKING | Reports computed lines/positions. |
| Layout PNG software preview | Yes | Terminal | Tests/code | WORKING | Renders a plan to a file using atlas/fallback measurements. |
| CLD1 layout descriptor codec | Yes | Backend/terminal | Tests/code | PARTIAL | Producer/codec exists; runtime consumer does not. |
| Custom in-game text renderer | No | Mode selectable | No | NOT WORKING | `CUSTOM_ENGINE` is intent only. |
| Renderer 1 runtime profile validation | Yes | Metadata/terminal | Tests/code | PARTIAL | Rejects stale/drifted profiles; version-specific. |
| Renderer 1 active-record capture | Yes | Backend | Tests/code | PARTIAL | Small validated snapshot of known record array. |
| Renderer 1 live position overrides | Yes | Backend | Tests/code | PARTIAL | Per-write readback and rollback; not a general renderer replacement. |
| Renderer 2 inspection | Partial | Visual Inspector | No | PARTIAL | Details/investigation only; editing unavailable. |
| Compressed asset stream discovery | Yes | Desktop/CLI | Yes | WORKING | Real MENUDAT list returned 32 blocks. |
| TIM 4bpp indexed decode/encode | Yes | Desktop/CLI | Yes | WORKING | Real Japanese assets displayed and round-trip tested. |
| TIM 8bpp indexed decode/encode | Yes | Desktop/CLI | Yes | WORKING | Real PROGDAT composite decoded and tested. |
| TIM 16bpp handling | Yes | Backend | Tests/code | PARTIAL | Supported by core codec; main visible workflow is indexed assets. |
| TIM 24bpp direct color | No | No | No | NOT WORKING | Explicitly unimplemented; no known case encountered. |
| Asset thumbnail browser/search | Yes | Desktop | Yes | WORKING | Searchable grid with real decoded images. |
| Asset metadata/provenance | Yes | Desktop | Yes | WORKING | IDs, offsets, sizes, format, semantics, capabilities, validation. |
| Palette/CLUT inspection | Yes | Desktop | Yes | WORKING | 16-color palette and usage hover details for 4bpp assets. |
| Raster text overlay | Yes | Desktop/CLI | Yes | WORKING | Japanese Start was replaced with `START`; both a rebuilt MENUDAT and a live in-emulator screenshot were produced. |
| Palette-preserving PNG export/import | Yes | Desktop/CLI | UI + tests | WORKING | Rejects wrong dimensions/unknown colors. |
| Composite background assembly/edit | Yes | Desktop | Yes | WORKING | Five 64x240 strips exposed as one 320x240 image. |
| Exact compressed-size budget | Yes | Desktop/CLI | Yes | WORKING | Blocks overflow and pads safe edits to consumed size. |
| Container rebuild | Yes | Desktop/CLI | Tests/code | WORKING | Changes edited blocks while preserving others. |
| Asset workspace/provenance journal | Yes | Desktop/backend | Tests/code | WORKING | Registers sources and records outputs/hashes. |
| Permanent disc image rebuild | No | No | No | NOT WORKING | Current UI builds a container, not a final patched image. |
| Temporary PCSX disc-file patch | Yes | Desktop/CLI | Code/tests | PARTIAL | Uses emulator API; no modified patch was applied in this audit. |
| Clear temporary emulator patches | Yes | CLI | Code/tests | PARTIAL | Not exposed in desktop inspector. |
| ISO9660/CD sector utilities | Yes | Backend | Tests/code | WORKING | Developer-only parsing/lookup helpers. |
| Current-screen VRAM capture | Yes | Visual Inspector | Yes | WORKING | Captured the genuine 320x240 live frame. |
| Static screen mapping overlays | Yes | Visual Inspector | Yes | WORKING | Main/system/spoils contexts; coverage still narrow. |
| Translation-only screen filter | Yes | Visual Inspector | Yes | WORKING | Filters mapped/live objects by text representation. |
| Manual mapping creation/deletion | Yes | Visual Inspector | UI + tests | WORKING | Registry persists; protected live mappings cannot be deleted. |
| Source-to-correct-inspector routing | Yes | Visual Inspector | Yes | PARTIAL | Asset route launches a real inspector; layout/Renderer 2 routes are informational/limited. |
| Cross-window asset selection | Yes | Desktop tools | Yes | WORKING | File-backed selection synchronization. |
| GPU ordering-table parsing | Yes | Backend | Yes | WORKING | Used during live correlation scan. |
| VRAM asset fingerprint detection | Yes | Backend | Yes | WORKING | Matches known assets against live VRAM. |
| GPU primitive/asset correlation | Yes | Visual Inspector | Yes | WORKING | Live scan found Start, Prepare, and classroom background. |
| Runtime lifecycle tracker | Yes | Visual/backend | Yes | WORKING | Load/upload/draw/stale/overwrite/unload provenance state machine. |
| Runtime page discovery | Yes | Visual/backend | Yes | PARTIAL | Learns asset-set pages; file-backed and specialized. |
| Runtime connection/setup UX | No | Status line only | Failure observed in code | NOT WORKING / NOT CONNECTED | Errors become empty badges/status text; no guided recovery. |
| Screen unknown-region visibility | Yes | Visual Inspector | Yes | WORKING | Unknown mappings remain visible rather than being hidden. |
| MIPS JAL/profile analysis | Yes | Backend/scripts | Tests/code | PARTIAL | Research/developer tooling, not user workflow. |
| Integrated end-to-end translation UI | No | No | No | NOT WORKING | Existing subsystems remain separate desktop, terminal, CLI, and emulator workflows. |
