# PS1 Localization Toolkit — Readiness Audit

Full-system evidence audit of the GCRTS reverse-engineering project
(game: *Twilight Syndrome: Tansaku Hen*, SLPS-00102), performed before
any consolidation into a reusable, game-agnostic toolkit. Every claim
below is backed by something read directly from the repository this
session — module contents, test runs, and the project's own
documentation — not by memory of earlier conversation. Evidence tiers
used throughout: `CONFIRMED_LIVE`, `STATIC_CODE_MATCH`,
`RUNTIME_DERIVED`, `TEST_VALIDATED`, `INFERRED`, `HYPOTHESIS`,
`UNKNOWN`, `DISPROVEN`.

Method: four parallel research passes gathered raw evidence (a full
module inventory of all 111 `gcrts`/`scripts` files; a documentation
consistency check across `docs/`; a classification of all 981 tests by
what they actually validate against; and a targeted search for
Twilight-Syndrome-specific logic leaking into generically-named
modules). This document is the synthesis of those four passes, not a
restatement of any one of them.

---

## 1. Executive summary

The project has real depth — 111 modules, ~21,700 LOC, 981 passing
tests — and several genuinely strong results (`XA_DECODER_VERIFICATION.md`'s
100.0000%-match against an independent FFmpeg decoder is the single
strongest evidence artifact in the whole codebase). But three findings
change how that depth should be read before building a toolkit on top
of it:

1. **The test suite is a regression net over recorded findings, not a
   live re-verification harness.** Of 981 tests, 958 (97.6%) are pure
   synthetic fixtures; only 10 touch real (but pre-extracted, not raw
   disc) game bytes; **zero** touch a running emulator. All genuine
   live/GDB evidence in this project comes from one-off manual scripts
   whose *conclusions* get frozen into test constants afterward — the
   test suite passing does not mean the game path still works today.
2. **The project's own canonical status document has drifted from
   itself.** `docs/status/CURRENT_SYSTEM_STATUS.md` contains at least
   five internal contradictions — most seriously, its own capability
   matrix still says Subtitles are "not started," directly contradicted
   by that same document's own narrative describing `subtitle_export.py`
   already producing a real `.srt` file this session. This must be
   fixed before the doc can be trusted as toolkit-planning ground truth.
3. **Game-specific leakage into generic-sounding infrastructure is
   narrower than expected, and localized.** Two real leaks were found
   (`gcrts/live_extract.py`, `gcrts/runtime_visual_provider.py`); the
   disassembler, ISO9660 reader, CD-ROM sector parser, and TIM decoder
   are all already clean, standards-based, and toolkit-ready as-is.

Net read: **the foundation is stronger than the surrounding narrative
suggests, but the narrative needs a truth pass before anyone trusts it,
and no one has yet proven the single most toolkit-relevant claim end
to end — that an edited line of text survives re-encoding, reinjection,
and actually renders correctly after a real boot.** See §20 for the
exact minimum blocking list, and §25 for the final call.

---

## 2. Current system architecture

The codebase already follows a workable, mostly-unintentional layering
that a toolkit extraction can build on rather than invent from
scratch:

- **Format primitives** (`gcrts/iso9660.py`, `gcrts/cdrom.py`,
  `gcrts/tim.py`, `gcrts/psx_ordering_table.py`, `gcrts/mips_disasm.py`,
  `gcrts/mips_jal_decoder.py`) implement real, documented PS1/ISO9660/
  MIPS standards with zero game-specific literals in their logic.
  These are already toolkit-grade `core/`.
- **Pure/testable domain logic** — the majority of modules take an
  *injected* `read_memory`/`data` callable or byte buffer rather than
  importing a live transport directly (`runtime_audio.py`,
  `renderer1_profile.py`, `overlay_identity.py`, `movie_detection.py`,
  `movie_loader_scan.py`, `mips_patch_profile.py`, and more). This is
  the right pattern and is already followed almost everywhere.
- **A small, identifiable live-transport layer** — only
  `gcrts/live_extract.py`, `gcrts/pcsx_patch.py`, `gcrts/runtime_probe.py`,
  `gcrts/screen_capture.py`, `gcrts/vram_asset_detector.py`,
  `gcrts/runtime_visual_provider.py`, plus the one-shot CLIs
  (`runtime_scan_cli.py`, `runtime_gpu_scan.py`) and all of
  `scripts/*.py`, actually open a socket or HTTP connection to GDB
  (port 3334) or the PCSX-Redux Web API (port 8080). This is a good
  sign: the emulator dependency is already mostly isolated, it just
  isn't cleanly *separated* from game-specific code in two places
  (§9, §15).
- **An investigation-narrative layer** — audio-discovery,
  audio-runtime-identification, and dialogue/semantic-database
  together are ~41% of the codebase (~8,970 LOC across 31 files) and
  read as a dated investigation log (milestone-by-milestone,
  documenting disproved hypotheses) rather than a stable API. This is
  valuable *history* but is the area most in need of separating
  "durable mechanism" from "investigation record" before toolkit
  extraction.
- **Two Tk GUI front-ends** (`asset_inspector_ui.py`,
  `visual_inspector_ui.py`) sit on top of the backend services, already
  separated from binary logic per their own docstrings.

---

## 3. Repository / subsystem inventory

| Subsystem | Main files/modules | Purpose | Current state | Evidence level | Major limitations |
|---|---|---|---|---|---|
| Text extraction/decoding | `script_decoder.py`, `loader.py`, `extractor.py`, `encoding.py`, `cluster.py` | Reverse-engineered dialogue bytecode decoder + generic multi-encoding text-run extraction | Implemented | `STATIC_CODE_MATCH` + `RUNTIME_DERIVED` (decoder traced to `FUN_80049168`) | Not yet merged with the external toolkit it was cross-validated against |
| Script encoding/reinjection | `script_encoder.py`, `validation.py`, `boundary_validation.py`, `live_injection.py`, `guarded_injection.py` | Re-encode edited text back to bytecode; guarded live RAM writes | Implemented | `TEST_VALIDATED` (synthetic) + `HYPOTHESIS` for full boot survival | No automated test proves a written edit survives past the write (§20) |
| Editable script representation | `editable_script.py`, `script_unit.py`, `editor_state.py` | JSON layer preserving control codes for a human translator | Implemented | `TEST_VALIDATED` | Depends on decoder fidelity above |
| Pointer handling | `control_code_index.py`, `control_position_risk.py` | Models a "mid-word split" control-code positioning bug | Documented root-cause | `RUNTIME_DERIVED` | Root cause modeled, not necessarily eliminated by the encoder |
| Font extraction | `glyph_atlas.py` | Character→glyph bitmap extraction, traced to `FUN_8004aa08` | Implemented | `STATIC_CODE_MATCH` | Fixed `16×16` glyph/`0x800a4c00` assumptions, this-game-specific |
| Glyph mapping | `glyph_char_map.py` | Code→Unicode table | Implemented | `INFERRED` from atlas | — |
| Font extension | `font_extension.py`, `font_workbench.py` | Add glyphs (272 codes) missing from base font | Implemented | `TEST_VALIDATED` | Offline only, no live-rendered proof |
| Text layout/fitting | `text_fitting.py`, `layout_validation.py`, `layout_plan_builder.py` | Reproduces the game's own word-wrap algorithm | Implemented | `RUNTIME_DERIVED` (`FUN_8004a370`) | `MEASURED_MAX_WIDTH_PX=280` is a single live-captured textbox, not general |
| Software preview/rendering | `layout_software_preview.py` | Draws real pixels from the glyph atlas, offline | Implemented | `TEST_VALIDATED` | Never cross-checked against a live in-game screenshot |
| Live RAM extraction | `live_extract.py` (`GdbClient`) | GDB remote-protocol client + script-buffer capture | Implemented | `CONFIRMED_LIVE` (used throughout this project) | Bundles a generic client with a game-specific address (§9) |
| Runtime tracing | `mips_patch_profile.py`, `scripts/gdb_cdinit_trigger_capture.py` | Per-executable patch profiles; breakpoint-triggered captures | Mixed | `LIVE_CONFIRMED_THIS_SESSION` for one executable only | Explicitly does not claim any other executable works (own docstring) |
| GPU/VRAM investigation | `vram_asset_detector.py`, `gpu_asset_correlation.py`, `psx_ordering_table.py` | Correlates decoded textures against real VRAM residency | Implemented | `CONFIRMED_LIVE` (for `PROG.EXE`) | `PROG.EXE`'s own primitive-submission mechanism still unidentified |
| Text rendering architecture | `render_mode.py`, `renderer1_profile.py`, `renderer1_runtime.py` | Native-renderer profile + live active-line detection | Renderer 1: `LIVE_VERIFIED` core; Renderer 2: `BLOCKED` | `CONFIRMED_LIVE` (Renderer 1 only) | Profile coverage 1 of ~15 executables; Renderer 2 trace never reproduced after first hit |
| Disc/LBA mapping | `iso9660.py`, `cdrom.py`, `xa_disc_index.py` | Real ISO9660 + CD-XA sector parsing; LBA→file resolution | Implemented | `CONFIRMED_LIVE` for the format itself | — |
| Executable analysis | `overlay_identity.py`, `mips_patch_profile.py` | 16-byte signature matching across ~15 loaded executables | Implemented | `CONFIRMED_LIVE` | Several executables share signatures (irreducibly ambiguous by this method alone) |
| MIPS-I disassembly | `mips_disasm.py`, `mips_jal_decoder.py` | General MIPS-I decoder + JAL target/return-address arithmetic | Implemented | `TEST_VALIDATED` + cross-checked against real disassembly | — |
| Static data-flow analysis | `movie_loader_scan.py` (`trace_register_backward`), `cdrom_fifo_scanner.py` | Bounded backward register tracer; CD FIFO read scanner | Implemented | `TEST_VALIDATED` (synthetic) + validated against real known cases | Straight-line only, not CFG-aware (documented limitation) |
| Audio asset discovery | `xapack.py`, `xapack_catalog.py`, `xa_disc_index.py`, `audio_asset_resolver.py` | Physical XA container format; full 43-file catalog | Implemented | `CONFIRMED_LIVE` (real bytes) | — |
| Audio decoding | `xa_decoder_verify.py` | XA-ADPCM decode vs. independent FFmpeg reference | `REFERENCE_VERIFIED` | `CONFIRMED_LIVE` | Strongest evidence artifact in the project |
| Audio runtime identification | `output_audio_match.py`, `audio_fingerprint.py`, `live_scene_identification.py` | WASAPI loopback capture → fingerprint → continuity → human confirmation | Implemented, per-asset | `CONFIRMED_LIVE` (`USER_LISTENING`) for 4 specific assets | Method proven, coverage is 4 assets, not general; a test comment cites a "real match" result with no corresponding test (§13, §23) |
| Dialogue/audio semantic DB | `dialogue_database.py`, `semantic_label_store.py`, `subtitle_export.py` | Confirmed-label persistence; `.srt` generation | Implemented | `TEST_VALIDATED` + one real `.srt` produced | Never rendered in-game — a file artifact, not a runtime overlay (§13) |
| Fandub groundwork | `audio_replacement.py` | Data model + validation-preview, explicitly no re-injection | Data model only | `HYPOTHESIS` | No replacement audio has ever been written back |
| Movie executable discovery | `movie_detection.py`, `overlay_identity.py` | Movie-player-family residency as the playback signal | Implemented | `CONFIRMED_LIVE` (`MOP.EXE`/`OP.STR`) | — |
| Movie table reconstruction | `movie_loader_scan.py` | 10-entry name table + pointer table per chapter | Implemented | `CONFIRMED_LIVE` (cross-verified per file) | 3 of 10 names are unshippped/cut content |
| Movie loader analysis | `movie_loader_scan.py` | Chapter→dispatcher→movie call-site recovery | Implemented | Mixed: 1 `CONFIRMED_LIVE`, 4 `STATIC_CODE_MATCH`, 2 `UNKNOWN` (`CAP2`/`CAP3`) | `CAPX.EXE`'s real selector source still `UNKNOWN` |
| Movie mapping | `MOVIE_CATALOG`, `AMBIGUOUS_GROUPS` | Chapter/exe→`.STR` file table | Partial | `CONFIRMED_LIVE` for 2 files, `AMBIGUOUS` for the rest | `MOVER.EXE`'s file pairing unresolved |
| Live movie confirmation | `live_movie_console_watch.py` | Console-text capture on movie-family entry breakpoints | Implemented (script) | `CONFIRMED_LIVE` for the cases it caught | Not integrated as an automated/CI-visible test (0 live tests, §14) |
| Project documentation | `docs/` (100+ files) | Investigation record + status ledger | Extensive | Mixed — see §7 | Internal contradictions inside the canonical status doc (§7) |
| Test infrastructure | `tests/` (87 files, 981 tests) | Regression suite | Green | `TEST_VALIDATED` only | 97.6% synthetic, 0% live (§14) |
| Evidence/confidence tracking | Per-module enums (`MovieMatchConfidence`, `VerificationSource`, `PatchProfileStatus`, …) | Ad hoc confidence tiers | Fragmented | — | No shared schema (§16) |
| GUI/editor/workbench | `asset_inspector_ui.py`, `visual_inspector_ui.py`, `editor_cli.py` | Tk desktop tools + terminal editor | Implemented | `TEST_VALIDATED` (backend) + manual (UI itself) | No automated UI tests (expected/acceptable) |

---

## 4. What is genuinely solved

Conservative list — only capabilities with real, reproducible evidence
beyond a single scene/slot/executable, or explicitly scoped as
single-purpose and correctly labeled as such:

1. **ISO9660 + CD-XA sector parsing** (`iso9660.py`, `cdrom.py`).
   *How*: implements the actual Primary Volume Descriptor / directory
   record spec and Mode2/2352 Form1/Form2 de-interleaving. *Evidence*:
   used successfully across every disc-reading module in the project
   (movie catalog LBAs, XAPACK catalog, font/CDB extraction) with no
   contradicting result found. *Tests*: synthetic, but structurally
   exercises the real spec. *Assumptions*: none game-specific — this
   is a real filesystem/format standard. *Reusable*: yes, directly.

2. **XA-ADPCM decoding** (`xa_decoder_verify.py`). *How*: decodes real
   XAPACK sectors and diffs sample-for-sample against an independently
   built FFmpeg reference decoder. *Evidence*: 100.0000% match, per
   `docs/status/CURRENT_SYSTEM_STATUS.md`'s own audio narrative —
   the single strongest evidence artifact this audit found anywhere in
   the project. *Reusable*: the ADPCM algorithm itself, yes (it's a
   real Sony/PS1-standard codec); the specific file cataloging around
   it is Twilight-Syndrome-specific.

3. **MIPS-I disassembly + JAL/branch arithmetic**
   (`mips_disasm.py`, `mips_jal_decoder.py`). *How*: general opcode
   decoder plus a purpose-built JAL target/return-address function,
   built after two real hand-computation bugs in this same project's
   own history. *Evidence*: `TEST_VALIDATED` (10+15 tests) and
   independently re-validated by successfully reproducing every
   already-known movie-loader finding (§ below) using the general
   scanner. *Reusable*: yes, this is real MIPS-I ISA logic with zero
   game content.

4. **Executable identity via code signature** (`overlay_identity.py`).
   *How*: reads a real 16-byte signature at each executable's own entry
   point. *Evidence*: `CONFIRMED_LIVE`, used successfully to
   distinguish ~15 different loaded executables sharing overlapping
   address ranges. *Limitation, stated honestly in its own docstring
   and confirmed by this audit*: several executables share identical
   signatures and are irreducibly ambiguous by this method alone — not
   a bug, a real hardware/compilation fact. *Reusable*: the mechanism
   (`identify_overlay(read_memory)`, `OverlayProfile` dataclass) is
   generic; `KNOWN_OVERLAYS`'s actual data is game-specific and
   correctly isolated in its own module.

5. **Movie runtime detection via overlay residency**
   (`movie_detection.py`). *How*: the movie-player executable family's
   mere residency (from #4 above) is itself the playback signal — no
   DMA tracing needed. *Evidence*: `CONFIRMED_LIVE`, a real 90-second
   opening-movie playthrough with the correct overlay resident the
   whole time. *Scope*: proven for one movie (`OP.STR`/`MOP.EXE`); the
   *mechanism* generalizes, the specific file mapping does not (yet).

6. **`CAP0.EXE`→`MPRO.EXE` movie-selection call site**
   (`movie_loader_scan.py`). *How*: a GDB breakpoint at the real
   dispatcher entry (`0x8006E5E4`) fired live with `$a1` read as
   exactly `8`, matching the independently-derived static prediction,
   and the live pointer-table bytes matched the disc image exactly.
   *This is the only movie-loader mapping with both static AND live
   confirmation* — every other chapter's mapping is static-only. *Scope*:
   one chapter, one save state; do not generalize to "movie loader
   solved" (see §5, §7).

7. **The audio-identification pipeline itself** (WASAPI loopback →
   fingerprint → offset-continuity → human listening,
   `output_audio_match.py`/`live_scene_identification.py`). *Evidence*:
   4 separate assets independently confirmed this way
   (`XAPACK22:7`, `XAPACK20:4`, `XAPACK08:3`, `XAPACK13:6`), each
   requiring actual human listening before being marked
   `USER_LISTENING` — never auto-confirmed from a score alone (a
   standing project rule, honored consistently in the code and
   memory). *Reusable*: the method (capture→fingerprint→continuity→
   human-gate) is fully game-agnostic; the reference database content
   is not.

8. **Static movie-loader architecture mapping method**
   (`movie_loader_scan.py`, `mips_disasm.py`). *How*: locate a shared
   debug string, walk backward to its containing function, recover a
   local pointer table, then backward-trace every call site's
   argument. *Evidence*: reproduced every already-known real finding
   from a prior manual investigation exactly (`TEST_VALIDATED` +
   cross-checked against real disc data), and was the tool that
   **caught its own author's wrong hypothesis** (the `CAPX.EXE`
   hand-off claim) via a live test it prompted. *Reusable*: the
   scanning technique (find dispatcher → find table → backward-trace
   argument) is genuinely general; only its literal `MOVIE_TABLE_NAMES`/
   `T_ADDR` data is game-specific, and is already cleanly isolated at
   module top.

---

## 5. What is partially solved

1. **Movie loader / mapping.** *Solved portion*: the architecture and
   method (§4.8); `CAP0`/`CAP1`/`CAP4` static mappings; `CAP0`'s live
   confirmation. *Not solved*: `CAPX.EXE`'s real selector source
   (proven NOT to be its one hardcoded call, real mechanism unknown —
   `DISPROVEN` hypothesis, `UNKNOWN` replacement); `CAP2.EXE`/`CAP3.EXE`
   have zero found call sites (`UNKNOWN` — trigger mechanism, if any,
   not located); `MOVER.EXE`'s file pairing (`AMBIGUOUS` between 2
   files). *Practical impact*: any movie-subtitle proof (§13) can only
   safely target `MOP.EXE`/`OP.STR` or `CAP0.EXE`/`MPRO.EXE` today.
   *Blocks Toolkit v0.1?* No, if v0.1 scope excludes movie authoring
   (§18). *Defer?* Yes for `CAPX`/`CAP2`/`CAP3`/`MOVER`, safely.

2. **Audio runtime identification, per-event.** *Solved portion*: the
   method (§4.7), 4 confirmed assets. *Not solved*: `xa_channel` is
   `POSITIONAL_UNCONFIRMED` per-event (per `CURRENT_SYSTEM_STATUS.md`'s
   own Audio matrix row); the code path that turns a resolved filename
   into an actual file read/open was never found; `classify_playback_backend()`
   currently returns `CD_INPUT_UNKNOWN_FORMAT`, an unresolved
   inconsistency with the separately-proven `classify_stream_format()
   → XA_ADPCM` result (documentation drift, see §7, not necessarily a
   code bug — the two functions answer different questions but the
   matrix conflates them). *Practical impact*: clean-condition
   identification works repeatably; identification "in the wild" for
   an arbitrary unconfirmed scene still requires the full manual
   capture workflow, not a one-shot lookup. *Blocks v0.1?* No, if
   audio is scoped as "identification only" in v0.1. *Defer?* Yes.

3. **Text/script reinjection.** *Solved portion*: decode → edit →
   re-encode is implemented and cross-validated (`RUNTIME_DERIVED`/
   `TEST_VALIDATED`); `live_injection.py`/`guarded_injection.py` can
   write to live RAM. *Not solved, and this is the audit's most
   important finding*: **no test or documented session in this
   repository demonstrates a full round trip** — edit a real line,
   re-encode it, inject it, and *observe it rendering correctly on
   screen after a real boot/reload*. `TEXT_ENGINE_ARCHITECTURE.md`'s
   own Phase 1 description states its layout-plan data model has "no
   game-side consumer for it yet." *Practical impact*: this is the
   single riskiest unproven assumption for a localization toolkit,
   whose entire point is exactly this round trip. *Blocks v0.1?*
   **Yes — this is the primary blocker in §20.** *Defer?* No.

4. **Renderer 1 / native text rendering.** *Solved portion*: live
   active-line detection and CLD1 layout-descriptor consumption,
   `CONFIRMED_LIVE`, for one executable. *Not solved*: profile
   coverage is 1 of ~15 known executables; Renderer 2's control-flow
   trace was hit once and never reproduced (`BLOCKED`). *Practical
   impact*: text rendering understanding is real but narrow; a second
   chapter/executable is not guaranteed to work without new
   investigation. *Blocks v0.1?* Only if v0.1 requires rendering
   validation across multiple chapters — a single-chapter proof can
   suffice for v0.1. *Defer?* Multi-chapter coverage, yes.

5. **Font extension / glyph handling.** *Solved portion*: glyph
   extraction and adding 272 missing glyphs, offline, `TEST_VALIDATED`.
   *Not solved*: never cross-checked against a real in-game rendered
   screenshot showing an added glyph displaying correctly. *Practical
   impact*: moderate risk that an added glyph looks right in the
   software preview but wrong in-game (palette/timing/VRAM upload
   details unverified). *Blocks v0.1?* Not strictly, but should be
   resolved before claiming font pipeline "done" (§9 font pipeline
   state). *Defer?* Partially — at least one live-rendered glyph check
   should happen before v0.1 ships a font-editing claim.

6. **Subtitle export.** *Solved portion*: a real `.srt` file was
   generated from a confirmed `DialogueDatabaseEntry`
   (`audio_export/fandub/XAPACK22_7/subtitle.srt`, per
   `CURRENT_SYSTEM_STATUS.md`'s own narrative). *Not solved*: this is a
   file artifact for an external player, not anything rendered through
   the PS1's own graphics path or an emulator overlay — Demo A (§13)
   has not been attempted at all. *Blocks v0.1?* No. *Defer?* Yes, if
   v0.1 doesn't promise in-game subtitles.

---

## 6. What remains unknown

### Blocking unknowns (must resolve before Toolkit construction)

- **Does an edited text line survive the full decode→edit→encode→
  inject→boot→render cycle?** Never demonstrated end to end (§5.3).
- **Is the internal documentation trustworthy as a planning baseline?**
  `CURRENT_SYSTEM_STATUS.md` currently contradicts itself on Subtitles
  status, test/module counts, and the Audio format-confidence question
  (§7). Must be corrected before using it as toolkit ground truth.
- **Where does the game-specific/generic boundary actually sit in
  `live_extract.py` and `runtime_visual_provider.py`?** Both currently
  bundle a reusable transport/orchestrator with hardcoded Twilight-
  Syndrome addresses and no override hook (§9, §15).

### Toolkit-design unknowns (don't block starting, shape interfaces)

- What minimal evidence/confidence schema should every discovery
  module adopt (§16) — currently ad hoc per module
  (`MovieMatchConfidence`, `VerificationSource`, `PatchProfileStatus`
  each independently invented similar but non-identical enums).
- Whether a unified `GameProject` data model is worth building now or
  only once a second game is attempted (§10).
- Whether `DEFAULT_DISC_PATH` and similar per-module defaults should
  route through an injected adapter config object rather than being
  redefined identically in multiple modules (`movie_loader_scan.py`
  and `audio_fingerprint.py` currently duplicate the exact same disc
  path string independently).

### Feature unknowns (can defer past v0.1)

- `CAPX.EXE`'s real movie selector source (§5.1).
- `MOVER.EXE`'s file pairing (§5.1).
- `CAP2.EXE`/`CAP3.EXE`'s movie trigger mechanism, if any (§5.1).
- Per-event `xa_channel` positional confirmation (§5.2).
- Renderer 1 profile coverage beyond one executable (§5.4).

### Research unknowns (interesting, not currently blocking)

- Whether the movie-loader scanner's dispatcher-finding heuristic (a
  format-string backward walk) generalizes to a differently-compiled
  second game, or whether it's tuned to this compiler's exact code
  shape.
- Whether `cdb_codec.py`'s specific RLE/LZ77/delta scheme is a
  reusable general-purpose PS1 codec or unique to this game's tools.
- SDB2.2/MS4/GP4 formats: `UNKNOWN`, "not located in any real file yet"
  per the capability matrix — open reverse-engineering, not a
  toolkit blocker.

---

## 7. Historical claims audit

| Old claim | Current status | Correct interpretation | Files requiring correction |
|---|---|---|---|
| `CAP0.EXE` hands off to `CAPX.EXE` to perform the actual movie load | `DISPROVEN` | A live breakpoint at `CAP0.EXE`'s own dispatcher fired with `$a1=8`; the same breakpoint at `CAPX.EXE`'s dispatcher never fired despite the movie fully playing. `CAP0.EXE` loads `MPRO.EXE` directly | **Already fully corrected** in `MOVIE_DETECTION.md`, `MOVIE_LOADER_ARCHITECTURE.md`, `CURRENT_SYSTEM_STATUS.md`, and `gcrts/movie_detection.py`'s own comments — verified this audit, no residual instance found anywhere else in the repo |
| Capability matrix: "Subtitles — UNSUPPORTED, not started" | Contradicted by the same document | `subtitle_export.py` exists and produced a real `.srt` this session, per the same document's own narrative section | `docs/status/CURRENT_SYSTEM_STATUS.md` (matrix row + "Subtitles" subsystem-detail section, both stale) |
| Headline: "biggest reverse-engineering gap: how `.STR` movie playback is triggered" | Contradicted by the very next bullet in the same document | Movie *runtime detection* is `RESOLVED`; only chapter-level *selection* mapping (a narrower, already-partially-solved question) remains open | `docs/status/CURRENT_SYSTEM_STATUS.md` headline section |
| Test/module counts: "981 passed... 103 modules, 86 test files" (headline) vs. "400 tests passing... 70 modules" (repo-health subsection, same file) | Both present, contradictory | Confirmed this audit: **981 is correct** (`py -m pytest tests/ -q` → `981 passed`); the 400/70 figures are stale | `docs/status/CURRENT_SYSTEM_STATUS.md` repo-health subsection |
| Audio bullet log ends at "478 passed" after the Captions milestone | Stale — headline is current through 981 | At least 8 later audio docs (`XA_DECODER_VERIFICATION.md`, `SEMANTIC_AUDIO_CLASSIFICATION.md`, `DIALOGUE_DATABASE.md`, `SUBTITLE_EXPORT.md`, and others) are missing from this bullet log though covered elsewhere in the same file | `docs/status/CURRENT_SYSTEM_STATUS.md` Audio subsystem-detail section |
| Capability matrix Audio row: `classify_playback_backend()` returns `CD_INPUT_UNKNOWN_FORMAT` (format unresolved) | Superseded, not corrected | A separate, later function `classify_stream_format()` independently resolved this to `XA_ADPCM` from real sector headers, and the decoder was `REFERENCE_VERIFIED` against it — the matrix cites the older/different API and reads as an open question that a newer result already answered | `docs/status/CURRENT_SYSTEM_STATUS.md` capability matrix |
| Several `docs/status/*.md` files (`GCRTS_FULL_SYSTEM_AUDIT.md`, `GCRTS_CHANGES_SINCE_1200.md`, `GCRTS_COMPLETE_WORK_SUMMARY_HE.md`, `current-system-snapshot/*`) present as current, dated 2026-08-09/10, citing 348/368 tests | Superseded snapshots, not labeled as historical in the folder index | These are frozen point-in-time artifacts; `docs/README.md`'s status/ listing doesn't warn a reader that only `CURRENT_SYSTEM_STATUS.md` is live | `docs/README.md`'s status/ section index (add an explicit "historical, do not treat as current" note) |
| A code-docstring citation chain to an earlier `NOTES.md` | The referenced file doesn't exist in this repo (per `docs/status/NOTES.md`'s own admission) | A broken evidence trail — some `gcrts/` docstrings may point at a source that's gone | Audit only; no single fix identified, flagged for awareness |

**Verification note**: the specific example the user's brief already
knew about (`CAP0.EXE`→`CAPX.EXE`) was checked exhaustively and found
**already fully corrected everywhere** — a genuine positive result, not
just an assumption. The remaining table rows are documentation-drift
findings from this audit's own pass, not previously known.

---

## 8. Text pipeline state

```text
disc/game files → discover text → decode → map glyphs →
edit Japanese→English → validate layout → encode → inject → boot/test
```

| Stage | State | Evidence |
|---|---|---|
| Discover text | Implemented | `extractor.py`/`cluster.py`, multi-encoding detection |
| Decode | Implemented | `script_decoder.py`, traced to `FUN_80049168`, cross-validated against an external toolkit and live RAM captures |
| Map glyphs | Implemented | `glyph_atlas.py`/`glyph_char_map.py` |
| Edit JP→EN | Implemented | `editable_script.py`/`editor_state.py`/`editor_cli.py` |
| Validate layout | Implemented | `text_fitting.py`/`layout_validation.py`, reproducing the real wrap algorithm |
| Encode | Implemented | `script_encoder.py` |
| Inject | Implemented (mechanism) | `live_injection.py`/`guarded_injection.py` |
| Boot/test | **Not proven** | No test or session demonstrates the injected result rendering correctly after a real boot — the single biggest gap in this whole pipeline (§5.3, §20) |

---

## 9. Font pipeline state

```text
discover font → decode glyphs → map glyph IDs →
add/replace English glyphs → rebuild font → inject → render correctly in game
```

Every stage through "rebuild font" is implemented and offline-tested
(`glyph_atlas.py`, `font_extension.py`, `font_workbench.py`,
`layout_software_preview.py`). **"Inject" and "render correctly in
game" are not live-proven** — no session or test shows an added glyph
displaying correctly on real emulated hardware. This mirrors the text
pipeline's own gap and should likely be resolved together (an in-game
render check naturally exercises both at once).

---

## 10. Audio/Fandub state

```text
disc scan → identify audio assets → map LBA/runtime playback →
associate dialogue → replace/rebuild asset → play modified voice in game
```

| Stage | State |
|---|---|
| Disc scan | `CONFIRMED_LIVE` — full 43-file XAPACK catalog |
| Identify audio assets | `CONFIRMED_LIVE` for 4 assets via the capture→fingerprint→continuity→human-listening method |
| Map LBA/runtime playback | Partial — file-level mapping solid; per-event channel positioning `POSITIONAL_UNCONFIRMED` |
| Associate dialogue | Implemented — `dialogue_database.py`, `semantic_label_store.py` |
| Replace/rebuild asset | **Data model only** — `audio_replacement.py` explicitly does validation-preview, no re-injection implemented |
| Play modified voice in game | **Not attempted** |

**Identification and replacement are at very different maturity
levels** — identification is real and repeatedly demonstrated;
replacement is an unbuilt data model. Any claim of "fandub pipeline"
readiness must distinguish these explicitly.

---

## 11. Movie pipeline state

```text
discover movie table → identify loader → recover mappings →
identify movie at runtime → manipulate/render during movie →
eventually subtitle/replace movie
```

| Stage | State |
|---|---|
| Discover movie table | `CONFIRMED_LIVE` — identical 10-entry table found and cross-verified in all 6 chapter executables |
| Identify loader | `CONFIRMED_LIVE` — dispatcher function located and disassembled |
| Recover mappings | Partial — 4 chapters mapped (1 live-confirmed, 3 static-only); 2 chapters (`CAP2`/`CAP3`) unmapped; `CAPX`'s real selector unknown |
| Identify movie at runtime | `CONFIRMED_LIVE` for the movie-player-family-residency method itself |
| Manipulate/render during movie | **Not attempted** |
| Subtitle/replace movie | **Not attempted** |

**Exact current boundary**: the project can reliably tell you *that* a
movie is playing and, for 2 of 7 real movie files, *which* one — but
has never touched anything about rendering onto or over a movie frame.

---

## 12. Runtime/rendering state

```text
tool-generated modification → launch emulator/game →
detect expected runtime behavior → collect evidence → classify confidence
```

Detection and evidence-collection are strong and largely automated for
*reading* runtime state (overlay identity, movie residency, VRAM
texture correlation, audio capture matching). The loop is **not**
automated end-to-end for *writing* a modification and confirming it —
every live-injection session found in this project was a manual,
one-off script run (§14), not a repeatable pytest-driven pipeline.
Renderer 1 is `CONFIRMED_LIVE` for exactly one executable; Renderer 2
is `BLOCKED`. No automated "make a change, launch, verify" loop exists
today for any subsystem.

---

## 13. Movie subtitle + gameplay overlay readiness

### Demo A — Movie subtitle

| Question | Answer |
|---|---|
| Known usable rendering functions | Renderer 1's CLD1 layout-descriptor consumption (`renderer1_runtime.py`) is the only `CONFIRMED_LIVE` rendering hook, and it's for regular dialogue text, not movie playback — unknown whether it's reachable while a movie-player executable (a *different* loaded overlay) is resident |
| Candidate hook points | None identified specifically for movie-time rendering; the movie-player executable family (`MPRO.EXE` etc.) has not been disassembled for its own rendering calls at all — out of scope for the movie-loader investigation, which deliberately did not analyze movie contents |
| Required RAM/VRAM resources | Unknown — no VRAM *write* path has been proven (only VRAM *read*, via `screen_capture.py`/`vram_asset_detector.py`) |
| Synchronization method | Unknown — no movie-time source (frame counter, timestamp) has been identified |
| Movie-time source | Not found |
| Risk of framebuffer overwrite | Real and unassessed — movies use double/streaming buffers whose ownership during playback is unexamined |
| GPU ordering concerns | Unassessed — Renderer 1's own primitive-submission mechanism for `PROG.EXE` is itself still unidentified (per the capability matrix), let alone for the movie-player family |
| Text encoding/rendering reuse | The glyph atlas/font-extension system *could* in principle supply glyph bitmaps, but nothing connects it to a movie-time render path |
| Minimal proof without solving every unknown | **Not currently possible as a real Demo A.** Every prerequisite (hook point, VRAM write, timing source) is unproven from zero. |

### Demo B — Gameplay overlay

| Question | Answer |
|---|---|
| Known usable rendering functions | Renderer 1 (`CONFIRMED_LIVE`, one executable) is a real, usable hook for on-screen text during regular gameplay |
| Candidate hook points | The same live-injection path already used for dialogue text (`live_injection.py`) is the most credible starting point |
| Required RAM/VRAM resources | Better understood than Demo A — the script buffer address and layout-descriptor mechanism are both real, `CONFIRMED_LIVE` findings |
| Synchronization method | Existing polling-based active-line detection (`renderer1_runtime.py`) could plausibly time a temporary message's appearance/removal |
| Risks | Lower than Demo A — no movie-specific framebuffer contention; still limited to the one profiled executable |
| Minimal proof feasibility | **More plausible than Demo A**, since it reuses machinery already proven live, but still requires an actual new experiment (temporary-message injection + timed removal) that has not been attempted |

**Readiness verdict**: Demo B is a credible, scoped next experiment
building on real `CONFIRMED_LIVE` infrastructure. Demo A would require
solving several genuinely unstarted unknowns (movie-time source,
VRAM write path, movie-executable disassembly) from zero — it is not
a "connect existing pieces" task the way Demo B is.

---

## 14. Tests and validation quality

**Confirmed count**: `981 passed, 0 failed` (`py -m pytest tests/ -q`,
run this session) — matches the project's own claim exactly.

| Bucket | Files | Tests | % |
|---|---|---:|---:|
| Synthetic (hand-built fixtures) | 81 | 958 | 97.6% |
| Real-disc (pre-extracted real asset containers, e.g. `MENUDAT.BIN`) | 4 | 10 | 1.0% |
| Mixed (synthetic + real in one file) | 2 | 13 | 1.3% |
| Live-emulator (GDB/PCSX-Redux Web API) | 0 | 0 | 0% |

```text
Test coverage: high (981 tests, broad module coverage)
Live coverage: effectively zero in the automated suite
Regression risk: real — a change could silently break the actual
  game-facing behavior while every test still passes, since almost
  nothing in the suite re-exercises real disc bytes or a live emulator
```

**Note none of the "real-disc" tests open the raw disc image
(`קיבצי דמה/...bin`) itself** — they open pre-extracted containers
already checked into `sdb_main_menu_asset/`. No test anywhere reads the
actual multi-GB disc image or makes a live socket connection.

**A specific integrity finding**: `test_audio_fingerprint.py` contains
a dangling comment referencing a test
(`test_match_candidate_finds_real_asset_and_offset`, "scoring 0.94+
against real disc audio") that **does not exist anywhere in the
repository**. A claimed real-audio validation result is cited in a
comment but is not actually captured by any automated test — a
concrete instance of exactly the "conclusion based on absence of
evidence" risk this audit was asked to hunt for (§23).

---

## 15. Game-specific leakage

| Module | Hardcoded assumption | Generic? | Should move to adapter? |
|---|---|---|---|
| `gcrts/live_extract.py` | `SCRIPT_BUF_ADDR = 0x801FE800` and `capture_script_buffer()`/`write_script_buffer()` share a module with the fully generic `GdbClient` (connect/`read_memory`/`write_memory`) | The `GdbClient` class itself is generic; the module as packaged is not | **Yes, highest priority** — split into a generic `gdb_client.py` and a game-specific `live_extract.py` built on top of it |
| `gcrts/runtime_visual_provider.py` | `_roots()` hardcodes `Path("sdb_main_menu_asset/PROG.EXE")`, `start=0x80049630`, a literal RAM-address list, and calls `SLPS00102_BASE_PROFILE`/`SLPS00102_AUDIO_PROFILE` inline rather than accepting them as constructor parameters | The class's own orchestration logic is generic; its defaults are not, and there's no override hook at all | **Yes** — should accept a profile via `__init__`, mirroring the parameter the underlying `renderer1_runtime.py`/`runtime_audio.py` functions already expose |
| `gcrts/movie_loader_scan.py`, `gcrts/audio_fingerprint.py` | Both independently redefine the identical `DEFAULT_DISC_PATH` string constant | Already overridable per-call, low severity | Should ultimately come from one shared adapter config object rather than being duplicated verbatim in two places (consistency risk, not a functional bug) |
| `gcrts/glyph_atlas.py` | `TABLE_RAM_ADDR`, fixed `16×16` glyph dimensions | Correctly scoped as font-specific per its own docstring | Only if a generic "indexed glyph table" abstraction is later built |
| `gcrts/text_fitting.py`, `gcrts/layout_validation.py` | `MEASURED_MAX_WIDTH_PX = 280`, `MAX_VISIBLE_LINES = 4` — both from a single live-captured textbox | Correctly scoped as engine-specific today | Yes, if genericized — needs to become a per-textbox parameter |
| `gcrts/overlay_identity.py`, `gcrts/movie_detection.py`, `gcrts/asset_registry.py`, `gcrts/xapack*.py` | Full literal executable-name/address/catalog tables | **Inherently and correctly game-specific** — this is each module's entire stated purpose | No — these are already the right shape for a game-adapter layer: a generic dataclass/matcher plus a game-supplied literal table |
| `gcrts/cdrom_fifo_scanner.py`, `gcrts/cdrom_driver_map.py` | Explicitly single-executable/single-address scope, stated plainly in their own docstrings | Correctly scoped, not masquerading as generic | No |
| `gcrts/mips_disasm.py`, `gcrts/mips_jal_decoder.py`, `gcrts/iso9660.py`, `gcrts/cdrom.py`, `gcrts/tim.py`, `gcrts/psx_ordering_table.py`, `gcrts/cdb_codec.py` (algorithm itself) | **Confirmed clean** — only game-specific literals appear in illustrative docstring prose, never in logic | Genuinely generic | Already toolkit-ready as-is |

**Bottom line**: leakage is real but narrow — 2 modules need a real
split/refactor (`live_extract.py`, `runtime_visual_provider.py`), a
handful of already-honestly-scoped game-specific modules need nothing
more than having their literal tables supplied by an adapter instead of
hardcoded inline (which most already do), and the true infrastructure
primitives are already clean.

---

## 16. Data/evidence model state

**Current state: fragmented, not unified.** Multiple independent
confidence-tier enums exist with similar but non-identical shapes:
`MovieMatchConfidence` (`CONFIRMED_LIVE`/`STATIC_CODE_MATCH`/
`NAME_MATCH`/`AMBIGUOUS`/`NONE`), `VerificationSource`
(`USER_LISTENING`/`RUNTIME_EVIDENCE`/`UNVERIFIED`), `PatchProfileStatus`
(6-value lifecycle state machine), and ad hoc string/bool flags
elsewhere. None of them share a base type, and no module stores a
structured `{claim, confidence, evidence: [...]}` record the way the
brief's example JSON shows — confidence lives *inside* domain-specific
dataclasses, not as a cross-cutting concern.

**Minimum architecture needed** (not a redesign — an additive shared
module): a small `gcrts/evidence.py` defining one shared
`Confidence` enum (the 8 tiers used throughout this audit) and an
`Evidence`/`Claim` dataclass pair, adopted incrementally by domain
modules that want it (e.g. `StaticMovieTrigger` could grow an
`evidence: list[Evidence]` field alongside its existing `confidence`
field) rather than a big-bang migration of every existing enum. This
is exactly the kind of task that's safe to do *during* toolkit
construction (§18), not a blocker.

---

## 17. Automation gaps

| Manual step | Automatable? | Necessary for v0.1? | Human confirmation desirable by design? |
|---|---|---|---|
| Selecting save states / navigating to a scene | Partially (state loading is already scriptable via the Web API) | No | No — this is pure mechanical setup, not a judgment call |
| Launching GDB / arming breakpoints | Yes, already scripted in most workflows (`scripts/*.py`) | No further work needed | No |
| Identifying which scene/chapter is active | Yes, via `overlay_identity`/`movie_detection` | Already done | No |
| Confirming a decoded text/audio match is correct | **No — by design** | N/A | **Yes** — this project's own standing rule (never auto-confirm audio from a score alone) is a deliberate quality gate, not a gap to close |
| Updating the semantic label store / dialogue database | Could auto-log candidates, but final confirmation should stay manual | No | Yes, for the same reason as above |
| Copying decoded text into the editor | Already automated (`editor_cli.py`, `editable_script.py`) | Done | No |
| Validating layout | Already automated (`layout_validation.py`) | Done | No |

**Principle applied consistently across the codebase already**: this
project does not automate the *judgment* steps (audio confirmation,
label acceptance) even where it easily could — that's intentional and
should be preserved in the toolkit, not "fixed."

---

## 18. Toolkit v0.1 minimum viable scope

Derived from the evidence above, not aspiration:

> **PS1 Localization Toolkit v0.1 — Twilight Syndrome reference adapter**

- Create/open a project (thin wrapper over existing disc/ISO9660
  reading — already solid, §4.1).
- Inspect disc structure and parse known executables (`iso9660.py`,
  `mips_disasm.py`, `overlay_identity.py` — all `CONFIRMED_LIVE`/clean).
- Discover known text/font structures and expose their confidence
  level explicitly (text pipeline is the most mature end-to-end
  candidate, §8).
- Edit text, validate layout (already implemented, §8).
- Reinject text — **but do not claim it's proven until the one
  end-to-end boot test in §20 is done.**
- Generate static analysis reports (movie-loader scanner, disassembly
  — already reusable, §4.3/§4.8).
- Optionally connect to PCSX-Redux for validation (transport layer
  already isolated, §2) — but scope this as "read-only validation," not
  "automated write-and-verify," since that loop doesn't exist yet
  (§12).

**Do not include in v0.1** (see §19): movie authoring, audio
replacement, or a polished GUI — none of these have the evidence base
the text pipeline does.

---

## 19. What should NOT be in v0.1

- Fully automatic arbitrary-PS1-game text detection (never attempted
  on a second game — §22).
- Generic movie replacement or subtitle authoring (Demo A readiness is
  Low, §13).
- Automated fandub replacement (data model only, no re-injection built
  — §10).
- Perfect runtime voice matching under background music (current
  method requires clean acoustic conditions and human confirmation by
  design — not a gap to "solve" for v0.1).
- Universal script-format inference (this project's decoder is
  reverse-engineered for one specific bytecode; nothing suggests
  generality yet).
- Arbitrary PS1 compression reconstruction (`cdb_codec.py`'s scheme is
  proven for this game's tools only).
- A polished GUI (existing Tk tools are functional developer tools,
  not consumer-facing — fine to leave as-is for v0.1).
- Automatic pointer relocation for every game (`control_position_risk.py`
  models one specific bug for one specific engine).

---

## 20. Blockers before Toolkit construction

**MUST DO BEFORE TOOLKIT — genuine blockers only:**

1. **Prove one real text modification survives the full reinjection
   cycle**: decode a real line → edit it → re-encode → inject live →
   reboot/reload → confirm on screen it rendered correctly. This is
   the toolkit's entire value proposition (§5.3, §8). **Both halves now
   have real, working mechanisms; one detail remains open** (full
   account: `docs/overlay_engine/GROUNDING_ANALYSIS.md` Stage 4):
   - *Renders correctly*: `CONFIRMED_LIVE`. An injected English
     sentence rendered legibly through the game's own renderer and
     font in real active dialogue (`evidence/stage4_text_injection_proof/after.png`),
     using the already-existing `gcrts.live_injection` pipeline.
   - *Survives reboot/reload*: a static disc-patching mechanism was
     found, built, and independently verified — a live dialogue line's
     exact raw bytes were located byte-for-byte inside the chapter's
     own `K1LINK.CDB` resource (stored as an uncompressed CDB-codec
     literal run), and a same-word-count translated replacement was
     written into a **copy** of the disc image
     (`gcrts.disc_text_patch`, `scripts/patch_disc_dialogue_text.py`).
     Re-reading that patched copy completely offline (no live emulator
     involved) correctly produced the translated line with the rest of
     the ISO untouched. **What's not yet confirmed**: that the running
     emulator, booted fresh from this copy, shows the translation
     during actual play — a save-state reload restores frozen RAM
     rather than re-reading disc, so this needs a genuine cold boot
     through real menu navigation, which needs controller input this
     project has never gotten working programmatically. That check
     needs a human at the controls.
2. ~~Fix `CURRENT_SYSTEM_STATUS.md`'s internal contradictions~~ —
   **done** (same pass that produced this audit): the Subtitles matrix
   row, the stale test/module counts, the movies headline redundant
   bullet, and the Audio format-confidence row were all corrected in
   place.
3. ~~Split `gcrts/live_extract.py`~~ — **done**:
   `gcrts/gdb_client.py` now holds the generic `GdbClient`;
   `live_extract.py` imports it for backward compatibility. See
   `docs/overlay_engine/GROUNDING_ANALYSIS.md`.
4. **Give `gcrts/runtime_visual_provider.py` a real override hook**
   for its game profile instead of hardcoded `PROG.EXE`/`SLPS00102_*`
   defaults with no parameter (§9, §15). **Still open** — a different
   module (`gcrts.pcsx_redux_adapter`) was built as a clean, adapter-
   ready alternative for the new overlay engine, but the pre-existing
   `runtime_visual_provider.py` itself was not modified.
5. ~~Adopt a minimal shared evidence/confidence type~~ — **done**:
   `gcrts/evidence.py` (`Confidence` enum, `Evidence`/`Claim`
   dataclasses), already adopted by the new
   `gcrts.runtime_context.RuntimeContextResolver`. See
   `docs/overlay_engine/GROUNDING_ANALYSIS.md`.

Two of five blockers remain open: the text-reinjection boot proof
(#1) and the `runtime_visual_provider.py` override hook (#4). Everything
else — movie subtitle demo, `CAPX`/`CAP2`/`CAP3`/`MOVER` resolution,
audio replacement, second-game validation — is real, valuable,
deferrable work, not a blocker.

---

## 21. Work that can happen during Toolkit construction

- Rename/reorganize modules into the proposed `core/`/`discovery/`/
  `localization/`/`runtime/`/`adapters/` tree (§22).
- Build a common CLI surface over the existing backend services.
- Add a project manifest format (JSON/YAML — see §10, no urgent need
  for SQLite given current data volumes).
- Migrate existing JSON stores (`semantic_label_store.py`,
  `dialogue_database.py`) into the unified project model incrementally.
- Improve documentation (beyond the specific §7 corrections that are
  blockers, general polish can happen alongside refactoring).
- Move remaining Twilight-specific configuration (disc path
  duplication, glyph dimensions) into the adapter layer.
- Expose scanner output (`movie_loader_scan.py`'s JSON database, etc.)
  through a unified interface.

---

## 21b. Recommended build order

```text
Phase 0 — Audit/freeze current behavior
  Objective: this document. Freeze what "current behavior" means
    before anything moves.
  Dependencies: none.
  Exit criteria: this audit exists and §20's 5 blockers are tracked
    as concrete tasks (done by writing this document).

Phase 1 — Fix the 5 blockers (§20)
  Objective: make the baseline trustworthy and prove the core value
    proposition before investing further.
  Dependencies: Phase 0.
  Exit criteria: one real text edit demonstrated end-to-end on
    screen; CURRENT_SYSTEM_STATUS.md's contradictions corrected;
    live_extract.py split; runtime_visual_provider.py takes a profile
    parameter; gcrts/evidence.py exists.

Phase 2 — Core abstractions
  Objective: formalize core/ (binary, mips, executable, disc,
    evidence, project_model) as an actual package boundary, not just
    a mental grouping.
  Dependencies: Phase 1 (evidence type must exist first).
  Exit criteria: mips_disasm.py, mips_jal_decoder.py, iso9660.py,
    cdrom.py, tim.py, overlay_identity.py's generic parts import
    cleanly from a core/ package with no adapter-specific imports.

Phase 3 — Twilight Syndrome adapter extraction
  Objective: move every literal table/address/path identified in §15
    (KNOWN_OVERLAYS, MOVIE_TABLE_NAMES, XAPACK catalog,
    DEFAULT_DISC_PATH, SLPS00102_* profiles, glyph dimensions) into
    one adapters/twilight_syndrome/ package.
  Dependencies: Phase 2.
  Exit criteria: grep for the game's own executable names/addresses
    outside adapters/twilight_syndrome/ returns only the already-
    correctly-scoped discovery modules (movie/audio/font detection),
    not core/.

Phase 4 — Unified project model
  Objective: build the GameProject model (§23) only now that the
    adapter boundary makes clear what it needs to reference.
  Dependencies: Phase 3.
  Exit criteria: existing JSON stores (semantic_label_store,
    dialogue_database, screen_mapping_registry) load into one
    GameProject without data loss.

Phase 5 — Discovery APIs
  Objective: expose text/font/audio/movie discovery through one
    consistent interface returning Evidence-tagged results.
  Dependencies: Phase 4.
  Exit criteria: a single CLI command can report "what's known about
    this project" across all four discovery domains, each result
    carrying a real confidence tier.

Phase 6 — Editing/reinjection APIs
  Objective: wrap the already-working encode/inject pipeline behind
    the project model, building on Phase 1's proof rather than
    re-deriving it.
  Dependencies: Phase 5, Phase 1's boot proof.
  Exit criteria: editing a text entry through the toolkit API and
    reinjecting it reproduces Phase 1's proof through the new
    interface, not just the original ad hoc path.

Phase 7 — Runtime validation
  Objective: build the automated "modify → launch → detect → record
    confidence" loop that §12 found doesn't exist yet.
  Dependencies: Phase 6.
  Exit criteria: at least one CI-runnable (or documented manual)
    validation loop exists for text reinjection, not just for
    read-only detection.

Phase 8 — Minimal CLI
  Objective: a single entry point over Phases 2-7's APIs.
  Dependencies: Phase 7.
  Exit criteria: create project → discover → edit → reinject →
    validate is one coherent command sequence, not five separate
    ad hoc scripts.

Phase 9 — Second-game validation
  Objective: the actual test of §27's central question.
  Dependencies: Phase 8.
  Exit criteria: a second PS1 game's project opens, and at minimum
    core/ requires zero changes to support it — only a new
    adapters/<game>/ package. Where this fails, that failure is
    itself the most valuable finding of the whole toolkit effort.
```

Movie-subtitle authoring (Demo A, §13) and full fandub replacement are
deliberately absent from this sequence — per §19, they don't belong in
v0.1 and can be scheduled as their own post-Phase-9 initiative once
their specific unknowns (movie-time source, VRAM write path, audio
replacement re-injection) are separately resolved.

---

## 22. Toolkit architecture readiness

Evaluating the proposed tree against actual code:

```text
core/
  binary       -> mips_disasm.py, mips_jal_decoder.py            [READY, clean]
  mips         -> same as above                                   [READY, clean]
  executable   -> overlay_identity.py's OverlayProfile/identify_overlay()
                  (generic mechanism) — KNOWN_OVERLAYS data moves to adapter
                                                                    [MOSTLY READY]
  disc         -> iso9660.py, cdrom.py                             [READY, clean]
  evidence     -> DOES NOT YET EXIST — needs building (§16)        [MISSING]
  project_model-> DOES NOT YET EXIST as a unified type (§10)       [MISSING]

discovery/
  text         -> extractor.py, cluster.py, encoding.py            [READY]
  fonts        -> glyph_atlas.py (parameterize addresses), font_extension.py
                                                                    [MOSTLY READY]
  audio        -> xapack.py, xa_disc_index.py, audio_fingerprint.py
                  (parameterize disc path)                         [MOSTLY READY]
  movies       -> movie_loader_scan.py, movie_detection.py         [READY, method generic, data game-specific]
  references   -> asset_registry.py-style patterns                 [game-specific by nature, correctly scoped]

localization/
  text         -> script_decoder.py, script_encoder.py, editable_script.py
                                                                    [READY, pending §20's boot proof]
  layout       -> text_fitting.py, layout_validation.py (parameterize width/lines)
                                                                    [MOSTLY READY]
  font         -> font_extension.py, font_workbench.py             [READY]
  audio        -> audio_replacement.py                             [DATA MODEL ONLY, not implemented]
  movies       -> NOTHING EXISTS for movie localization yet         [EXPERIMENTAL/future]

runtime/
  pcsx_redux   -> pcsx_patch.py, screen_capture.py, runtime_probe.py
                                                                    [READY]
  gdb          -> live_extract.py's GdbClient (needs splitting, §15) [NEEDS REFACTOR]
  capture      -> output_audio_capture.py, screen_capture.py        [READY]
  validation   -> NOTHING AUTOMATED EXISTS (§12) — all manual today  [MISSING as automation, present as manual method]

adapters/
  twilight_syndrome/ -> KNOWN_OVERLAYS, MOVIE_TABLE_NAMES, XAPACK catalog,
                        DEFAULT_DISC_PATH, SLPS00102_* profiles       [DATA EXISTS, currently scattered — needs consolidating here]

cli_or_gui/
  -> editor_cli.py, asset_inspector_ui.py, visual_inspector_ui.py, asset_cli.py
                                                                    [READY, already separated from binary logic]
```

**Verdict on the proposed structure**: broadly correct and achievable
without a rewrite — most modules already sit at approximately the
right layer, just not yet physically reorganized. The two real gaps
are `core/evidence` (build new) and `runtime/validation` (does not
exist as automation; exists only as manual method, §12) — both
additive, not blocking.

---

## 23. Data model audit

Current persistent project data is fragmented across several
independent JSON stores with no common parent type: glyph mappings
(in-code tables), script/dialogue records (`editable_script.py`'s own
JSON shape), audio mappings (`dialogue_database.py`,
`semantic_label_store.py`), movie mappings (`STATIC_MOVIE_TRIGGERS`,
in-code, not persisted as project data at all yet), runtime symbols
(`mips_patch_profile.py`'s `PatchProfile` registry, JSON-persistable),
evidence/confidence (no dedicated store, §16), disc assets
(`asset_registry.py`, `asset_project.py`), scene labels
(`screen_mapping_registry.py`).

**Is fragmentation actually a problem yet?** Moderately — each store
works fine in isolation and none contradict each other, but there's no
single place a toolkit user could open to see "everything known about
this project" in one view. A unified `GameProject` model (as sketched
in the brief) is **justified but not urgent** — it's squarely
Phase-3-during-construction work (§21), not a blocker. Plain JSON
(matching every existing store's own choice) remains the right format
given current data volumes; nothing here needs SQLite yet.

---

## 24. Confidence/evidence architecture

Covered in depth in §16. Restated briefly: the *tiers* used throughout
this audit and this project's own domain modules are consistent in
spirit (everyone independently converged on something like
`CONFIRMED_LIVE`/`STATIC`/`AMBIGUOUS`/`UNKNOWN`) but not consistent in
*implementation* — no shared type. Minimum fix: one new module, no
migration required, adopted incrementally.

---

## 25. Real-game versus synthetic validation

Cross-project classification (extending §14's test-specific finding to
every scanner/decoder):

| Component | Synthetic fixture | Real TS binary | Multiple real executables | Runtime behavior |
|---|---|---|---|---|
| `mips_disasm.py` | Yes | Yes (via movie_loader_scan cross-check) | Yes (6 chapter executables) | No |
| `movie_loader_scan.py` | Yes (own test suite) | **Yes** — recovered every known real mapping | Yes, 6 files independently | Yes — `CAP0.EXE` case only |
| `iso9660.py` | Yes | Yes (used by every disc-reading module) | Yes | N/A (static format) |
| `xa_decoder_verify.py` | N/A | Yes | Yes (multiple XAPACK files) | N/A (offline decode) |
| `overlay_identity.py` | Yes | Yes | Yes (~15 executables) | Yes |
| `audio_fingerprint.py`/`output_audio_match.py` | Yes | Yes | 4 assets | **Yes** — the only subsystem with genuine, repeated live-emulator validation, done manually |
| `script_decoder.py` | Yes | Yes (cross-validated against external toolkit) | Partial | No |
| `renderer1_runtime.py` | Yes | Yes | **One executable only** | Yes |
| `glyph_atlas.py`/`font_extension.py` | Yes | Yes | One font | No |

**Key distinction reinforced**: `movie_loader_scan.py` should not be
considered proven merely because its own synthetic fixtures pass — it
is credible *because it also independently recovered every previously
known real mapping* and was the tool that surfaced a live-testable,
falsifiable prediction (which then got confirmed). This is the
standard the rest of the "confirmed" list in §4 was held to as well.

---

## 26. Automation readiness (expanded — see §17 for the table)

Nothing new beyond §17; restated for report-structure completeness.
The short version: reading/detection is largely automated; writing/
verifying a modification is not automated anywhere in this project
today, and the judgment steps that *are* manual are manual by design,
not by neglect.

---

## 27. Second-game portability criteria

**Ideal criterion** (per the brief): supporting a second game should
mostly require a new adapter, not a Core rewrite.

**Systems most likely to pass this test as-is**: `mips_disasm.py`,
`mips_jal_decoder.py`, `iso9660.py`, `cdrom.py`, `tim.py` — genuine
standards, zero game content.

**Systems most likely to fail this test today**:
- `cdb_codec.py` — its specific control-byte RLE/LZ77/delta scheme was
  reverse-engineered from this game's own tools; nothing suggests
  another PS1 game's custom container format would match it.
- `glyph_atlas.py` — fixed `16×16` glyph dimensions and table address
  are this font's own layout, not a PS1-wide convention.
- `movie_loader_scan.py`'s *dispatcher-finding heuristic* (walk
  backward from a known format string to a function prologue) is
  encouragingly general in *technique*, but has only ever been run
  against one compiler's output from one game — untested whether it
  generalizes to a differently-compiled second game's binaries.
- Any module whose "generic-sounding" name masks per-game literals
  not yet parameterized (`live_extract.py`, `runtime_visual_provider.py`,
  §15) will need that split done *before* a second game can reuse them
  at all.

**This has never been tested** — no second game has been attempted.
Until it is, "the architecture is generic" remains a `HYPOTHESIS`, not
a `TEST_VALIDATED` claim, regardless of how clean the current single-
game code looks.

---

## 28. Risk matrix

| Risk | Probability | Impact | Evidence | Mitigation |
|---|---|---|---|---|
| Hidden game-specific assumptions in "core" modules | Low (confirmed narrow, §15) | Medium | Direct search found only 2 real leaks | Fix the 2 identified modules (§20) |
| Documentation drift causing wrong planning decisions | **High — already happened** | Medium-High | 5 concrete contradictions found in one document (§7) | Fix `CURRENT_SYSTEM_STATUS.md` before using it as a baseline |
| False confidence from synthetic-only tests | **High** | Medium-High | 97.6% synthetic, 0% live in the automated suite (§14) | Add at least one automated smoke test that exercises real disc bytes per major subsystem; treat "tests pass" and "game path works" as separate claims |
| Text-reinjection round trip silently broken | Unknown (untested) | **High** — this is the toolkit's core value proposition | No test/session proves it either way (§5.3) | Do the boot proof (§20 item 1) before broader toolkit investment |
| Movie/audio subsystems overclaimed as "solved" | Medium | Medium | Multiple `AMBIGUOUS`/`UNKNOWN` items still open (§5, §6) | Keep confidence tiers visible in any toolkit UI/report, not just in code comments |
| Pointer/text-size expansion breaking layout | Medium | Medium | `control_position_risk.py` documents a known bug class, not eliminated | Treat as a known constraint in the localization workflow, not solved |
| Movie framebuffer overwrite during a future subtitle attempt | Unknown (never tested) | High if attempted | No VRAM-write path proven at all (§13) | Don't attempt Demo A until VRAM write + movie-time source are separately proven |
| Emulator-only behavior not matching real hardware | Unknown | Medium | All validation this project has done is PCSX-Redux-specific | Out of scope for v0.1; flag as a known limitation, not a blocker |
| Regression during refactor into toolkit layout | Medium | Medium | 981 tests provide a real (if partial) safety net | Keep the test suite green through every refactor step; add smoke tests for the 2 leakage modules before splitting them |
| Second-game assumptions wrong | Unknown (untested) | High for that goal specifically, zero for v0.1 | No second game attempted (§27) | Defer past v0.1; treat as its own validation milestone |

---

## 29. Readiness / probability assessment

```text
Ready to begin Core/adapter refactor:        High
  — the primitives (disasm, ISO9660, CD-ROM, TIM) are already clean;
    the 2 real leaks have a clear, small fix.

Ready for text-focused Toolkit v0.1:         Medium-High
  — every stage through "encode" is solid; the one missing proof
    (§20 item 1) is well-defined and bounded, not open-ended research.

Ready for movie subtitle authoring (Demo A): Low
  — requires solving several genuinely-unstarted unknowns (VRAM write,
    movie-time source, movie-executable disassembly) from zero.

Ready for gameplay overlay (Demo B):         Medium
  — reuses real CONFIRMED_LIVE infrastructure; the remaining work is
    a scoped new experiment, not new reverse-engineering.

Ready for full fandub replacement:           Low
  — identification is real; replacement is an unbuilt data model with
    no re-injection path at all.

Ready for arbitrary PS1 games:               Low
  — never tested; several modules (cdb_codec.py, glyph_atlas.py) are
    almost certainly this-game-specific in their actual algorithms,
    not just their data tables.
```

**Likely required effort for each open area:**

- `CAPX.EXE` selector, `CAP2`/`CAP3` mapping, `MOVER.EXE` pairing:
  **additional reverse engineering** (bounded — same method as already
  used for the solved chapters, just needs the right save state/scene).
- Text-reinjection boot proof: **minor implementation** — the pieces
  exist, this is executing and observing an existing pipeline, not
  building a new one.
- Evidence model, `live_extract.py`/`runtime_visual_provider.py` split:
  **minor implementation** — small, mechanical, low-risk changes.
- Movie subtitle Demo A: **major architectural work** — multiple
  unstarted unknowns, not a refactor.
- Second-game portability: **unknown until attempted** — could be
  minor (if the architecture really is clean) or major (if `cdb_codec.py`/
  `glyph_atlas.py`-style algorithms turn out to be more game-specific
  than they look); genuinely can't be estimated without trying.

---

## 30. Contradiction and assumption hunt (red-team pass)

Actively searching for reasons the current understanding could be
wrong, beyond what's already covered above:

- **Two documents describing the same system differently**: found —
  `CURRENT_SYSTEM_STATUS.md`'s capability matrix vs. its own narrative
  sections describe Audio format-confidence and Subtitles status
  differently within the *same file* (§7), the most concerning
  instance since it's not even cross-file drift, it's self-drift.
- **Code contradicting documentation**: none found this pass beyond
  the already-corrected `CAPX.EXE` hand-off case (§7) — a genuinely
  positive result, though the audit's scope (4 research passes, not a
  line-by-line reconciliation of all 111 modules against all 100+ docs)
  means this isn't an exhaustive guarantee.
- **Tests encoding obsolete behavior**: `test_audio_fingerprint.py`'s
  dangling comment (§14) is a concrete instance — a claimed result
  with no corresponding test, which is a milder but related failure
  mode to "obsolete behavior still tested."
- **Scanners silently depending on known answers**: worth flagging —
  `movie_loader_scan.py`'s synthetic test suite necessarily encodes
  the *shape* of patterns already known from the real disc (§14's own
  test file docstring says as much: built to mirror real patterns
  found elsewhere). This is reasonable engineering, not a flaw, but
  means the synthetic suite's passing is not independent evidence the
  scanner would find a *differently-shaped* real pattern (e.g. in a
  second game, §27).
- **Evidence tiers used inconsistently**: confirmed, §16/§24 — three
  different modules each invented a similar-but-not-identical enum
  independently, which is itself evidence no one has been enforcing a
  single standard.
- **Claims based on a single observed event**: the `CAP0.EXE`→`MPRO.EXE`
  live confirmation (§4.6) is exactly this — one breakpoint hit, one
  save slot. It's real evidence, correctly tiered as `CONFIRMED_LIVE`
  rather than something stronger, but a toolkit consumer should
  understand "confirmed" here means "witnessed once," not "load-bearing
  under all conditions."
- **Conclusions based on absence of events**: `CAP2.EXE`/`CAP3.EXE`
  having "zero call sites found" (§5.1) is being correctly reported as
  `UNKNOWN`, not misreported as "these chapters don't trigger movies" —
  checked specifically and confirmed the existing documentation already
  avoids this trap for this case. The dangling test-comment case (§14)
  is the inverse failure mode (a claim with no evidence at all,
  presented as if validated) and is the sharper finding of the two.

---

## 31. Final decision

### **B — Ready after a small defined proof**

Not A: the project's own status documentation currently contradicts
itself in ways that would mislead toolkit planning if used as-is
(§7), and the single most toolkit-relevant claim — that a text edit
survives reinjection and renders correctly — has never been
demonstrated (§5.3). These are not open research questions; they are
concrete, boundable tasks.

Not C: nothing found in this audit suggests the underlying
architecture is wrong. The primitives are clean (§4, §15), the
leakage is narrow and well-understood (§15), the proposed toolkit
layout is broadly achievable without a rewrite (§22), and the biggest
open items (movie selector edge cases, audio channel positioning) are
scoped, deferrable feature work, not architecture-invalidating risks.

**Exact minimum tasks to reach A** (identical to §20, restated as the
final checklist — updated to reflect work done in the same pass that
produced this audit and in the immediate overlay-engine follow-up,
`docs/overlay_engine/GROUNDING_ANALYSIS.md`):

1. Run one real edit through decode→encode→inject→boot→visual
   confirmation, end to end, and record the result honestly whichever
   way it comes out. **Nearly done**: decode→encode→inject→render
   confirmed live (`evidence/stage4_text_injection_proof/`); a static
   disc-patching mechanism for the →reboot→ half was found, built, and
   verified offline (`gcrts.disc_text_patch`) — a translated line
   correctly persists in a patched disc-image copy, independently
   re-read with no live emulator involved. **Still open**: confirming
   the running emulator shows it after an actual cold boot, which
   needs real controller navigation this project has no automated way
   to do — a human-in-the-loop step, not further engineering.
2. ~~Correct `CURRENT_SYSTEM_STATUS.md`'s five identified internal
   contradictions (§7).~~ **Done.**
3. ~~Split `gcrts/live_extract.py`'s generic `GdbClient` out of its
   game-specific script-buffer code.~~ **Done** (`gcrts/gdb_client.py`).
4. Give `gcrts/runtime_visual_provider.py` a constructor-level profile
   override instead of hardcoded defaults. **Still open.**
5. ~~Add one shared `Confidence`/`Evidence` type (`gcrts/evidence.py`)
   before more ad hoc enums accumulate.~~ **Done.**

Two of five remain open (#1, #4). None of these require new reverse
engineering or unsolved research —
they are executable this week, not open-ended.
