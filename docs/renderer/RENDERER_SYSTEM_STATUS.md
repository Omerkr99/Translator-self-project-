# Renderer System Status

**Audit date:** 2026-08-09  
**Scope:** repository-wide analysis only; no code or runtime implementation was changed.  
**Authority rule:** the 2026-08-09 section at the top of `CURRENT_SYSTEM_STATUS.md` and sections 10-22 of `RENDERER_LIVE_PROOF.md` supersede older investigation conclusions where they conflict.

## Reading the status labels

- **LIVE VERIFIED** — demonstrated against a running game, with direct readback and/or reversible visible proof.
- **STATIC CONFIRMED** — established from code, disassembly, file structure, or a deterministic offline round trip, but not demonstrated as that behavior in a running game.
- **IMPLEMENTED** — code exists and is tested; this does not imply that the game calls it.
- **IMPLEMENTED BUT NOT CONNECTED** — usable host-side code exists, but no automatic runtime consumer connects it to visible rendering.
- **PARTIAL** — some links or cases are proven and others are not.
- **EXPERIMENTAL** — research or framework code whose runtime validity is limited.
- **UNKNOWN** — the repository contains no sufficient evidence.
- **RULED OUT** — a specific hypothesis was directly disproved.
- **STALE** — an older claim contradicted by newer, stronger evidence.

## Executive answer

Renderer 1 is the game's directly written `POLY_FT4` glyph path whose source-of-truth placement is a 14-byte per-glyph record. It is confirmed for ordinary dialogue, photo/portrait-inset dialogue, and the A/B/C choice UI in the tested overlays. Its position path is solved well enough to move real glyphs and two real lines manually, including descriptor-driven centering. It is not integrated automatically into normal gameplay.

Renderer 2 is the convenient project label for a structurally separate GTE `RTPT`/`RTPS` quad-building path. It is not merely another caller of Renderer 1 because it builds coordinates through a different front end. It fired once during atmospheric narration. Its source records, callers across overlays, content coverage, and full chain are not mapped. The label does not yet prove that every non-Renderer-1 text path belongs to one unified second renderer.

## 1. Renderer 1

### What it is and where it is used

Renderer 1 is the direct glyph-position writer discovered in the currently tested, unidentified overlay. For each glyph it reads X/Y from a 14-byte record, copies those values into one of two alternating `POLY_FT4` primitive buffers, and submits the primitive through the shared `addPrim`/ordering-table path.

Confirmed situations:

- ordinary/plain conversation dialogue;
- portrait/photo-inset dialogue;
- the full-screen A/B/C choice UI associated with the photo sequence;
- animated text-adjacent glyphs such as the selection cursor and continue/wait icon use the same record/primitive ecosystem.

The earlier claim that photo-inset and choice content use a distinct renderer is **STALE**. The zero-hit test occurred after settled text stopped being redrawn. A later live session caught this content on the same writer and produced visible edits. Renderer 1 must not be generalized to atmospheric narration, system text, chapter titles, or every overlay without further evidence.

### Confirmed chain

Addresses below are **overlay-specific evidence**, not portable constants:

```text
14-byte glyph position record
  base 0x800A2AD4 + glyph_index * 0x0E     [LIVE VERIFIED, tested overlay]
  X = +0x08; Y = +0x0A                     [LIVE VERIFIED]
        |
        v
shared direct writer around RAM:800397BC-800397D0
  lhu X/Y from $s1; sh X/Y into $s0        [LIVE VERIFIED, overlay-specific]
        |
        v
40-byte POLY_FT4 in alternating buffers    [LIVE VERIFIED]
  A: 0x800BBE48..0x800BC2A7
  B: 0x800D0A5C..0x800D0EBB                [overlay-specific]
        |
        v
addPrim 0x800774B4                          [LIVE + STATIC CONFIRMED]
        |
        v
Ordering Table linked list                  [LIVE VERIFIED]
        |
        v
DrawOTag -> GPU                             [STATIC CONFIRMED/shared PS1 path]
```

`addPrim` links the primitive by reference rather than copying it. A known text primitive address was observed as its `$a1` argument. OT direction was verified newest-first, and a one-node splice caused a real visible change. `DrawOTag` wrapper/implementation addresses recorded for another overlay are `0x800767F4`/`0x80076818`; they must not be assumed valid in this writer's active overlay.

The GTE quad builder at `0x8007B224` and call site `0x8004500C` belong to Renderer 2, not Renderer 1. Older diagrams that put the GTE builder in Renderer 1's front end are superseded.

### The 14-byte per-glyph record

| Offset | Observed value/behavior | Classification | Meaning |
|---|---|---|---|
| `+0x0` | `index * 16` across the captured line | **LIKELY** | Running per-character counter/index. The pattern is confirmed; its complete semantic purpose is not. |
| `+0x2` | `0x0000` in the sample | **UNKNOWN** | Reserved or unused in that sample only. |
| `+0x4` | `0x0015`, constant per captured line | **LIKELY** | Font/glyph-set or line attribute ID; never varied experimentally. |
| `+0x6` | `0x7FC0`, constant | **UNKNOWN** | A clip/scale/sentinel interpretation is speculation. |
| `+0x8` | proportional sequence such as 10, 26, 38, 52... | **CONFIRMED: X** | Read before the primitive X store. Live editing moved an animated glyph horizontally and arbitrary X placement was verified. |
| `+0xA` | 152 on line 1, 171 on line 2 | **CONFIRMED: Y** | Exact match to scanned screen coordinates; a live edit pushed only one glyph/line off-screen and restoration brought it back. |
| `+0xC` | `0xFFFF` in the sample | **UNKNOWN** | Sentinel, terminator, or unused slot is unproven. |

The record stride is exactly `0x0E`. X and Y are proven by causal live edits, propagation into the primitive, screenshots, and clean restoration—not merely by coordinate-shaped values.

### Live verification already completed

- Direct X editing and direct Y editing.
- One glyph moved independently and placed at an arbitrary absolute coordinate.
- One complete 11-glyph line moved by a rigid X/Y delta; proportional spacing remained intact for eight seconds.
- Two 12-character lines moved independently using different deltas from one decoded `CLD1` descriptor; all 24 X/Y pairs were read back.
- Left-positioned descriptor output reached real pixels.
- Center alignment reached real pixels using the descriptor's resolved X.
- Two alternating primitive destinations, each containing two 14-slot line blocks, were mapped.
- The source record propagated to the primitive, then to `addPrim` and the OT.
- OT link direction and a one-node splice were proven.
- Static settled text can stop passing through the writer; animated cursor/icon elements continue to redraw.
- Immediate screenshots can capture a stale frame, and quickload/overlay changes can invalidate addresses.

### Remaining Renderer 1 gaps

- No automatic runtime hook/dispatcher reads an active descriptor and continuously applies it.
- No production mapping exists from the active script buffer/`ScriptUnit` to the correct descriptor.
- Active line and glyph-to-record detection are manual/research procedures.
- The named executable and robust fingerprint for the proven record base are unknown.
- Real glyph advance widths were not used in the live centering proof.
- Lines 3-4 lack safe source-record/primitive allocation proof.
- No automatic handling exists for wraps, line transitions, settled versus redrawn text, or double-buffer lifecycle.
- No verified cross-overlay address/profile set exists.
- Glyph selection still comes from the established original/HOST_FITTED content path; the `CLD1` proof is position-only.
- No persistent disc patch or real-hardware verification exists.

## 2. Renderer 2

### Evidence that it is separate

Renderer 2 is the GTE quad front end:

```text
overlay-specific call site 0x8004500C
  -> 0x8007B224
     -> lwc2 three vertices; GTE RTPT
     -> lwc2 fourth vertex; GTE RTPS
     -> four SXY stores forming a POLY_FT4
```

This is not just another caller of Renderer 1. Renderer 1 copies scalar X/Y fields from `$s1` records directly into primitive memory. Renderer 2 invokes a GTE transform-based quad builder. They can converge later at the generic `addPrim`/OT/GPU machinery, but their position computation and primitive staging are structurally different.

The old proof based on Renderer 1's writer not firing during photo/choice content is **STALE** and cannot support separation. The valid separation evidence is the distinct GTE implementation itself plus the later live narration hit.

### Situations using it

- **LIVE VERIFIED once:** atmospheric narration during the “Hanako-san” urban-legend sequence—multi-line white/colored text over a dark background.
- **Not proven:** all narration, all four-line text, chapter titles, other overlays, or any ordinary dialogue category.

### Known, suspected, unidentified

**Known:** the quad-builder structure; one live call-site hit during atmospheric narration; the front end is distinct; eventual primitive submission is expected to use the game's common OT/GPU infrastructure, though the complete live narration chain was not captured.

**Suspected:** the narration overlay swapped out before revalidation; the one hit likely belongs to a scene-specific overlay. This is a strong explanation, but the executable identity was not captured.

**Unidentified:** text/script source, glyph lookup, per-glyph or per-vertex state, position record format, exact active caller/profile, primitive destinations, line handling, centering, and automatic integration point.

### Is it definitely one renderer?

No. “Renderer 2” is a useful label for the one GTE/RTPS path, not evidence that every remaining UI/text case shares it. System prompts, status overlays, speaker labels as independent objects, menus outside the tested A/B/C UI, and chapter titles remain adapter stubs or uninvestigated. Additional renderer variants may exist; the repository does not justify naming a Renderer 3 yet.

### Exact blockers

1. Reproduce a known narration scene on demand.
2. Identify/fingerprint the active executable before the overlay changes.
3. Re-derive and validate the call site, GTE store, and submission addresses in that overlay.
4. Trace backward to its text/glyph/position source and forward to its live primitive/OT entry.
5. Perform a reversible causal position edit.
6. Determine whether other narration/UI situations share the same path.

## 3. Renderer-variant assessment

| Situation | Current classification | Evidence limit |
|---|---|---|
| Plain dialogue | Renderer 1 | Live writer hits and live movement. |
| Photo/portrait dialogue | Renderer 1 | Newer evidence supersedes an earlier zero-hit false negative. |
| A/B/C photo choice UI | Renderer 1 | Source-record edits moved/removed individual visible elements. |
| Atmospheric narration | Renderer 2 | One GTE call-site hit only; chain incomplete. |
| Four-line narration | Possibly Renderer 2 | Observed in the narration context, but line-specific causality was not traced. |
| Generic choice menus | Unknown | Only the specific A/B/C UI is classified. |
| Speaker labels | Partial/dialogue-associated | Control codes are decoded; no separate render path is proven. |
| System prompts/status overlays/chapter titles | Unknown | Registered only as unimplemented adapters. Some title text may be baked into images. |
| Alternate overlays | Partial | Layout drift is confirmed; named renderer profiles are not. |

The two-renderer model is sufficient as a working map of the two proven front ends, but not as a complete taxonomy of all game text.

## 4. CLD1 today

`CLD1` is GCRTS's version-1 `LayoutDescriptor`: a host-authored, little-endian binary format. It is not an original game format.

### Ownership and content

- The editor/data layer creates an `EditorLayoutPlan` manually or through `layout_plan_builder`.
- `layout_descriptor.encode_layout_descriptor()` serializes it.
- The 18-byte header contains magic/version, line and character counts, origin, flags, and page-transition metadata.
- Each fixed 10-byte line record contains character slice, final resolved X/Y, alignment metadata, and flags.
- A trailing stream contains the game's existing 16-bit glyph codes.
- Alignment is resolved on the host at encode time; the stored X is final.

### Injection and consumption

`layout_descriptor_injection` implements a guarded plan for writing descriptor bytes to a profile's reserved region and then publishing a pointer, with readback. In the current checked-in `mips_patch_profiles.json`, however, even the one live-positive anonymous profile has `pointer_slot_addr`, `descriptor_region_addr`, and size set to `null`, so the repository does not presently contain a reusable configured injection target.

The earlier MIPS diagnostic stub only checked `CLD1` magic and wrote a marker. It was not a renderer. The current Renderer 1 visible proof decoded `CLD1` on the host and manually wrote its resulting X/Y to live position records. No game runtime code automatically parses or consumes `CLD1` today.

### What is proven

- **CLD1 format works:** yes—golden/round-trip tests and real host encode/decode.
- **One-line positioning works:** yes—live, position-only.
- **Two independently positioned lines work:** yes—live, 24 records.
- **Centering works:** yes—live using fallback widths and a host-resolved X.
- **Automatic runtime integration works:** no.
- **Editor automatically controls gameplay:** no; debugger/host RAM writes remain required.

## 5. Renderer 1 data flow

```text
Editor text
  --[IMPLEMENTED]-->
EditorLayoutPlan
  --[IMPLEMENTED / STATIC CONFIRMED]-->
CLD1 LayoutDescriptor
  --[IMPLEMENTED BUT CURRENT PROFILE TARGETS ARE UNCONFIGURED]-->
descriptor injection into RAM
  --[NOT IMPLEMENTED: no production per-unit lookup]-->
runtime descriptor lookup
  --[NOT IMPLEMENTED]-->
active ScriptUnit / line / glyph mapping
  --[LIVE VERIFIED MANUALLY; NOT AUTOMATED]-->
14-byte glyph position record
  --[LIVE VERIFIED]-->
X/Y fields
  --[LIVE VERIFIED]-->
direct writer into POLY_FT4
  --[LIVE VERIFIED]-->
addPrim
  --[LIVE VERIFIED]-->
Ordering Table
  --[STATIC CONFIRMED; shared draw path]-->
DrawOTag
  --[CONFIRMED PLATFORM PATH]-->
GPU
```

The combined `EditorLayoutPlan -> CLD1 -> decoded X/Y -> visible glyph` chain was **LIVE VERIFIED as a manual research procedure**, not as an installed autonomous runtime chain.

## 6. Renderer 2 data flow

```text
text/script state
  --[UNKNOWN]-->
glyph and position/vertex state
  --[UNKNOWN]-->
overlay-specific call site
  --[LIVE VERIFIED ONCE]-->
GTE RTPT/RTPS POLY_FT4 builder
  --[STATIC CONFIRMED]-->
visible text primitive
  --[PARTIAL: earlier OT evidence; narration chain not captured end-to-end]-->
shared addPrim / Ordering Table
  --[LIKELY SHARED, NOT LIVE-TRACED FOR THE NARRATION HIT]-->
DrawOTag
  --[CONFIRMED PLATFORM PATH]-->
GPU
```

## 7. Responsibility map

| Responsibility | Owning modules/data | Status and scope |
|---|---|---|
| Disc/XA extraction | `cdrom`, `iso9660`, `loader`, `extractor`, `cluster` | Generic GCRTS core; disc structure and extraction confirmed. |
| CDB resources | `cdb_codec`; external `cdb.py`/`rle.py` | Twilight-Syndrome-specific codec/container; independently cross-validated. |
| Script decoding | `script_decoder`, `editable_script`, `script_unit`, `live_extract` | Game-specific; GCRTS table is less complete than external `linkdec.py`. |
| Script encoding | `script_encoder`, `editable_script`, `live_injection` | Game-specific; HOST_FITTED live path is established. |
| Control-code handling | `control_policy`, `control_position_risk`, `control_code_index` | Game-specific policy/indexing; external toolkit has broader opcode coverage. |
| Font/glyph lookup | `glyph_char_map`, `glyph_atlas` | Game-specific; width-table access exists; live blob requirements remain. |
| Font extension | `font_extension`, `font_workbench` | Live-session feature; not persistent on disc. External toolkit supports offline expanded-font patching. |
| Text fitting | `layout_validation`, `text_fitting`, `boundary_validation` | Mostly reusable planning with game-specific constants/control risks. |
| Editor planning/state | `editor_layout_plan`, `layout_plan_builder`, `layout_preview`, `layout_software_preview`, `editor_state`, `editor_cli` | Generic editor/core concepts with Twilight-specific defaults and glyph codes. |
| CLD1 generation | `layout_descriptor`, `CUSTOM_LAYOUT_DESCRIPTOR.md` | GCRTS-specific format; implemented and tested. |
| Runtime profile detection | `mips_patch_profile`, `mips_jal_decoder`, JSON registry | Framework implemented; real named coverage absent. |
| Live text injection | `live_extract`, `live_injection`, `guarded_injection` | HOST_FITTED whole-buffer pipeline; does not automate position records. |
| CLD1 injection | `layout_descriptor_injection` | Implemented guard/readback framework; current registry lacks usable regions. |
| Renderer 1 positioning | Research logs/manual GDB/Lua procedure | Live proven, not packaged as runtime production code. |
| Renderer 2 positioning | Research logs only | Mostly unknown. |
| GPU primitive creation | Game overlay code; Renderer 1 direct writer, Renderer 2 GTE builder | Twilight-specific reverse-engineered logic. |
| OT submission | Game `addPrim`/`DrawOTag` path | Shared PS1/game runtime behavior. |
| Persistent rebuild | External toolkit `build.py`, `merge.py`, `patch.py`; no equivalent complete GCRTS path | External/offline path only; not proven here as a complete rebuilt bootable image. |
| Multi-text adapters | `render_paths` | Dialogue implemented; other families are honest stubs. |

## 8. Renderer 1 capability table

| Capability | Status | Missing piece or qualification |
|---|---|---|
| Move one glyph | **YES — LIVE VERIFIED** | Reversible X/Y and arbitrary coordinate proof. |
| Move a complete line | **YES — LIVE VERIFIED** | Manual host writes. |
| Control X | **YES — LIVE VERIFIED** | Correct breakpoint must precede X load. |
| Control Y | **YES — LIVE VERIFIED** | Manual host writes. |
| Control two lines independently | **YES — LIVE VERIFIED** | 12+12 records; not automatic. |
| Center a line | **YES — LIVE VERIFIED** | Fallback widths only. |
| Preserve proportional spacing | **YES — LIVE VERIFIED** | Rigid line delta preserves game's existing spacing. |
| Compute new proportional spacing | **PARTIAL** | Host width APIs exist, but automated per-glyph live application does not. |
| Use true glyph widths | **PARTIAL** | `GlyphAtlas` width lookup is implemented/static-confirmed; live CLD1 centering used fallback 8/16 widths. |
| Support English | **PARTIAL** | HOST_FITTED and live font injection support exists; CLD1 position proof reused existing glyphs and is session-only. |
| Support Japanese | **YES — IMPLEMENTED BUT MANUAL** | Existing game glyphs/text render; custom positions require manual writes. |
| Support lines 3-4 | **NO** | Game maximum is statically confirmed, but safe records/primitives/OT allocation are not. |
| Arbitrary line starts | **YES — IMPLEMENTED BUT MANUAL** | Descriptor X/Y can drive starts; no runtime hookup. |
| Arbitrary line breaks | **PARTIAL** | Editor plans and control-aware HOST_FITTED fitting exist; live record lifecycle/mapping is not automated. |
| Arbitrary per-glyph placement | **YES — IMPLEMENTED BUT MANUAL** | One-glyph live proof; CLD1 is line-oriented and no automatic per-glyph dispatcher exists. |
| Runtime automatic descriptor consumption | **NO** | No installed parser/dispatcher/lookup. |
| Multiple executables/overlays | **NO** | No named live-confirmed Renderer 1 profile. |
| Persistent disc patch | **NO** | GCRTS has no completed BIN/CUE rebuild/custom-position patch. |
| Real hardware output | **UNKNOWN** | Evidence is PCSX-Redux only. |

## 9. The automation gap

Manual RAM proof answers “can these coordinates control pixels?” Automatic integration must answer “which coordinates should be applied, to which currently active records, at which safe moment, in any supported overlay?”

The runtime path still must:

1. identify and fingerprint the active executable/overlay;
2. validate every address and instruction landmark before writing;
3. locate the descriptor for the active script unit rather than use a fixed diagnostic pointer;
4. associate the live script buffer/cursor with a `ScriptUnit`;
5. detect the active line and its character range;
6. map each current glyph to `base + index * 0x0E` safely;
7. apply line X/Y while preserving or recomputing proportional advances;
8. use the correct overlay's real glyph-width table;
9. handle wraps, line transitions, cursor/continue icons, and settled text;
10. write at a lifecycle point that survives both primitive buffers;
11. support only surveyed lines/slots and never overwrite adjacent UI primitives;
12. detect overlay/layout drift after scene changes or savestate loads;
13. fall back to original/HOST_FITTED behavior on any unsupported or invalid state;
14. cleanly disable custom layout without leaving hooks, pointers, or RAM edits behind.

## 10. Profiles and overlay state

### Actually live-confirmed

- `UNIDENTIFIED_SESSION_2026-07-27`: diagnostic CLD1-magic hook/canary fired. Executable identity is unknown. Its current JSON entry has no descriptor/pointer region configured.
- The 2026-08-09 Renderer 1 record base and writer chain: live-confirmed in an unidentified active overlay, stable across several scenes and a process relaunch, but not captured as a named registry profile.

Therefore **zero named executable profiles are truly verified**, and there is **one anonymous positive hook profile plus one anonymous live Renderer 1 layout** that may or may not be the same executable state.

### External/static or unverified

- `CAP0.EXE` through `CAP4.EXE`, `CAPX.EXE`, `MNINO.EXE`, `MPRO.EXE`, `MRIKA.EXE`, and `MYOKO.EXE` are present in the registry as unverified with null addresses.
- The external toolkit supplies static `fonttbl`, `fontcnt`, `linktbl`, and `linkcnt` for CAP0-CAPX and shared `fontbuf`/`linkbuf` values. These are useful executable-specific data addresses, not verified Renderer 1 hook/record profiles.
- `UNIDENTIFIED_SECOND_CHARACTER_2026-07-27` is confirmed not firing for the tested hook/layout; it is a negative result, not support.

### Drift behavior and implication

The live layout changed among shifted chapter-0, original chapter-0, and chapter-1 mappings, including during ordinary transitions. Savestates replace executable/overlay RAM. Previously safe scratch memory was later occupied. Absolute addresses alone are unsafe.

Automatic detection needs stable executable fingerprints, current instruction-byte/JAL validation, renderer-specific addresses, record base/stride, safe memory regions, and invalidation/re-detection after every load or transition.

## 11. External Twilight Syndrome toolkit

The separate toolkit under `קיבצי דמה/twilight_syndrome-main` is reference code, not part of `gcrts`.

### What it solves better today

- A substantially more complete script control-code assembler/disassembler.
- Working CDB outer-container handling and the same inner codec as GCRTS.
- Full two-level font lookup and atlas decoding.
- Per-chapter CAP0-CAPX font/link table metadata.
- Offline script/font building, merging, executable patching, and expanded-font support.

### Independently verified against the disc

- CAP0 executable/link/font assets were extracted at the documented sizes.
- `fontdec` produced a legible real atlas.
- `linkdec` produced 190 coherent paragraphs, 163 containing text/control structure.
- The `PRESS`/`0x8500` bit layout agrees with GCRTS's live control-code findings.
- Its CDB codec/container model agrees with GCRTS's independent implementation.

### Adopted versus reference-only

GCRTS independently has `cdb_codec`, ISO extraction, script models, and glyph-width access. The report history describes the codec as independently arrived at, not copied. The repository does not show wholesale porting of the toolkit's full control table, complete outer CDB build pipeline, font atlas pipeline, or disc patch/rebuild system into `gcrts`.

All CAP INI files and the remaining toolkit module interfaces were included in this audit. Deeper behavioral validation of `fontdb.py`, `mkfont.py`, `merge.py`, `build.py`, `linkcfg.py`, and `dec.c` would still be worthwhile before porting or trusting a bootable rebuild. This is engineering reference review, not a prerequisite for Renderer 1 position automation.

### What it does not solve

It preserves the original renderer and replaces compatible data. It does not implement live editor-controlled X/Y, CLD1 consumption, active-line mapping, Renderer 1 automation, Renderer 2 discovery, or safe cross-overlay runtime hooks.

## 12. Tests and repository health

- The requested `CONTROL_CODE_POLICY.md` document is absent. The corresponding implementation evidence is `gcrts/control_policy.py`, supported by `tests/test_control_policy.py`; it should not be confused with a missing prose specification.
- The newest successful recorded run is **294 passed, 0 failed** on 2026-08-09 with Python 3.13 and a workspace-local pytest temp root.
- This audit counted **294 test functions** in 29 test files, consistent with that result.
- This audit could not rerun them: neither `py` nor `python` resolves to an installed interpreter in the current shell. Therefore “294 passing” is recent recorded evidence, not a fresh execution result.
- Eleven Python modules have no same-named dedicated test: `__init__`, `cli`, `editable_script`, `encoding`, `font_extension`, `glyph_atlas`, `glyph_char_map`, `live_extract`, `loader`, `script_decoder`, and `script_encoder`. Some are exercised indirectly; emulator I/O and the manual renderer proof remain the critical unautomated areas.
- `README.md` says 43 tests and is stale.
- Markdown output visibly contains mojibake/encoding corruption in arrows, punctuation, and Japanese text.
- `pcsx.lua` is only 2 bytes; `vram-viewer.lua` is empty. The documented `scratchpad/*.py` capture tools and `erase_glyphs_native.lua` are absent from the repository.
- Git has **no commits and zero tracked files**. All 52 top-level status entries are untracked; there is no baseline commit, diff history, or safe Git rollback.
- Save states, memory cards, emulator configuration, generated shaders, caches, crash/runtime data, extracted disc files, and a raw disc image are mixed with source and documentation.
- No code was changed during this audit. This report is the sole added artifact.

## 13. Stale / superseded findings

| Old claim | Current verified state | New evidence |
|---|---|---|
| Screen-position writer is unknown. | **STALE:** Renderer 1 source record and direct writer are mapped. | `RENDERER_LIVE_PROOF.md` §§10-14; `CURRENT_SYSTEM_STATUS.md` 2026-08-09 update. |
| Record `+8/+A` does not affect visible output. | **STALE:** earlier tests edited a destination copy or used the wrong breakpoint timing. X/Y causality is live proven at `$s1`. | Live proof §§10-12. |
| CLD1 is not connected to visible positioning. | **STALE:** decoded CLD1 X/Y drove real pixels manually. | Live proof §§16, 19, 20. |
| Phase 9 is blocked on finding Renderer 1's writer. | **STALE:** discovery is done; automatic integration is the blocker. | Current status top update and live proof §§11-16. |
| Photo-inset dialogue and A/B/C choices use Renderer 2. | **STALE:** they use Renderer 1; settled text caused zero-hit false negatives. | Current status superseding note around its later Renderer discussion; live proof §§10-12. |
| The GTE path's content is unidentified. | **PARTLY STALE:** one atmospheric narration hit identifies at least one use; broader coverage remains unknown. | Live proof §22. |
| Primitive buffer edits should persist if synchronized. | **STALE:** the buffer is overwritten from the 14-byte source record. | Live proof §10. |
| A simple two-buffer, 14-slot model. | **STALE:** two alternating destinations each contain two 14-slot line blocks. | Live proof §14. |
| `char23 + 0x28` is a free next-line primitive. | **RULED OUT:** it is the active continue/wait icon. | Live proof §21. |
| Candidate D/static template is the screen source. | **RULED OUT:** deterministic same-frame edits propagated but did not move visible text. | `VISIBLE_DIALOGUE_COMPOSITION_PATH.md`; `TEXT_POSITION_TRACE_LOG.md` event H. |
| Test suite has 43/185/200/243/279 tests. | **STALE:** newest recorded result is 294 passing. | Current status and live proof cleanup. |
| One address layout can be reused across scenes/chapters. | **RULED OUT:** overlay drift occurred repeatedly. | `MASTER_RENDER_MODE_MAP.md` drift log; profile docs. |

## 14. Remaining work by renderer

### Renderer 1 — dependency order

1. **Automation prototype:** host-side or reversible hook-driven application to one active line at the correct writer lifecycle point.
2. **Identity/profile:** capture the active executable fingerprint and formalize its writer/record/submission landmarks.
3. **Descriptor lookup:** map active script unit to a validated CLD1 descriptor; remove fixed diagnostic-pointer assumptions.
4. **Active mapping:** detect current line, glyph index, record group, cursor/icon exclusions, and settled/redrawn state.
5. **Metrics:** connect the correct real width table/`GlyphAtlas` to live placement and centering.
6. **Two-line robustness:** automate independently positioned lines and both primitive buffers.
7. **Lines 3-4:** discover natural allocations or survey safe primitive storage and OT insertion; do not guess adjacent slots.
8. **Safety/fallback:** revalidation, rollback, overlay-drift handling, and clean fallback to original/HOST_FITTED.
9. **Overlay generalization:** repeat the full proof and fingerprinting per supported executable.
10. **Persistence:** only after runtime behavior is robust, design/test an on-disc patch and rebuild.

### Renderer 2 — separate reverse-engineering order

1. Reproduce atmospheric narration reliably.
2. Fingerprint its active overlay before transition.
3. Revalidate the GTE call site and trace backward to source position state.
4. Trace forward through primitive and OT for that same hit.
5. Perform one reversible X/Y causal edit.
6. Classify which narration/UI cases share this path before designing integration.

Renderer 2 discovery must not delay Renderer 1 automation.

## 15. Project roadmap

- **Stage A — Renderer 1 automatic prototype:** one identified profile, one active line, decoded CLD1, reversible automatic record update.
- **Stage B — Renderer 1 robust two-line layout:** active line/glyph mapping, real widths, centering, buffer lifecycle, fallback.
- **Stage C — Profiles and overlay generalization:** fingerprints, drift detection, revalidation, multiple verified executables; investigate safe lines 3-4 separately.
- **Stage D — Renderer 2 investigation/integration:** reproduce narration, map and causally verify its position path, then decide whether CLD1 can target it.
- **Stage E — Persistent disc workflow:** adopt/port vetted external script/font/rebuild knowledge and prove a bootable BIN/CUE patch.
- **Stage F — Broader PS1 adapter architecture:** replace stubs only as each additional text family is live classified.

## 16. Explicit answers

**What exactly is Renderer 1?** The direct writer that copies X/Y from a 14-byte per-glyph record into double-buffered `POLY_FT4` glyph primitives for confirmed dialogue and A/B/C UI cases.

**What exactly is Renderer 2?** The project's label for a separate GTE `RTPT`/`RTPS` quad-builder path, live-hit once during atmospheric narration. Its complete text-position implementation is unknown.

**Is Renderer 1 already solved?** Its visible position mechanism is solved for one unidentified overlay. Automatic, safe, profile-aware integration is not.

**What part is solved and what is not?** Record base/stride, X/Y fields, primitive propagation, two-line manual control, centering, and OT submission are solved. Runtime descriptor lookup, active mapping, real-width application, profiles, lines 3-4, fallback, and persistence are not.

**Can CLD1 already move real text?** Yes, live, through host decoding followed by manual RAM application.

**Can CLD1 already center real text?** Yes, live with fallback widths; not yet with real measured glyph widths.

**Can the editor do this automatically during normal gameplay?** No.

**What prevents that today?** No dispatcher/hook connects the active unit and descriptor to the correct live line/glyph records, and no named profile safely identifies those addresses.

**Are lines 3-4 safe?** No. Four is a confirmed engine maximum, not a confirmed allocation. The guessed adjacent slot was an active icon.

**Are real glyph widths already used?** They can be used by host code when a valid atlas is supplied, but the live CLD1 centering proof used fallback widths and the automatic runtime path does not exist.

**How many profiles are truly verified?** Zero named executable profiles. One anonymous diagnostic-hook profile is positive, and one anonymous Renderer 1 layout was live verified but not registered as a named portable profile.

**Do we still need to find the screen-position writer?** Not for Renderer 1. Yes, effectively, for Renderer 2 because its source-to-visible chain remains unmapped.

**What is the single most important engineering task now?** Build a reversible one-profile automatic Renderer 1 prototype that maps one active line from decoded CLD1 to the 14-byte records with validation and fallback.

**What is the single most important reverse-engineering task now?** Reproduce atmospheric narration and capture/fingerprint Renderer 2's active overlay so its position source can be traced.

**What should not be worked on yet?** A permanent disc custom-renderer patch, speculative Renderer 3 taxonomy, or guessed lines 3-4 primitive allocation before Renderer 1 automation and profile safety exist.

## Where the system stands now

- Renderer 1 is a direct 14-byte-record-to-`POLY_FT4` glyph path.
- Its X/Y fields and visible causality are live verified.
- Ordinary, photo-inset, and A/B/C dialogue UI use Renderer 1 in tested scenes.
- One glyph, one full line, and two independent lines have been moved live.
- CLD1 has driven real positions and fallback-width centering manually.
- Renderer 1's primitive buffers, `addPrim`, and OT link are mapped.
- Two lines are proven; lines 3-4 are unsafe/unproven.
- No automatic CLD1 runtime consumer exists.
- No named executable renderer profile is live verified.
- Real width lookup exists host-side but was not used in live centering.
- Renderer 2 is a distinct GTE path with one atmospheric-narration hit.
- Renderer 2's source records and complete chain remain unknown.
- The external toolkit is strong for scripts/fonts/offline patching, not custom positioning.
- The newest recorded suite is 294/294, but this shell lacks Python for a fresh run.
- Git has no commit or tracked baseline, and runtime artifacts are mixed with source.

### Renderer 1

**Solved:** causal X/Y placement, record layout/stride, visible primitive propagation, manual one/two-line control, descriptor-driven left/center positioning.  
**Missing:** automatic active-unit/line/glyph mapping, trustworthy profiles, real-width live application, safe lines 3-4, fallback/generalization, persistence.

### Renderer 2

**Solved:** distinct GTE builder exists and fires for at least one atmospheric narration scene.  
**Missing:** reproducible scene/profile, text/position source, full primitive/OT trace, causal edit, coverage classification, integration.

### Next engineering task

Implement one reversible, validated, one-profile Renderer 1 automatic CLD1-to-position-record prototype.

### Next reverse-engineering task

Reproduce atmospheric narration and fingerprint/trace Renderer 2's active overlay from source position state to primitive.

### Current biggest risk

Treating anonymous absolute addresses as portable despite proven overlay and savestate-driven layout drift.
