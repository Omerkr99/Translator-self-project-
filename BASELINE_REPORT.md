# Baseline Report — Text-Injection Pipeline

Snapshot taken before starting the Alternative Text Engine / Editor-Controlled
Rendering Pipeline work (master prompt, 2026-07-27), per that spec's Phase 0
requirement. This records the state of the repository *before* any Phase 1
model is added, so later work has a fixed point to diff against and so the
"components that must remain unchanged" list is explicit rather than implied.

## Test baseline

```
161 passed in 0.60s
```

Command: `py -m pytest tests/ -q` from the repo root. All 161 tests pass with
no warnings, no skips. This is the number every later phase's "all previous
tests still pass" requirement is measured against.

## Module inventory

### Core pipeline (the modules the master prompt names explicitly)

| Module | Purpose |
|---|---|
| `script_decoder` | Parses the raw 16-bit word stream from the live script buffer into `ScriptCode` objects (character / control / end), classified by family (A/B) and subtype. Owns `CONTROL_A_MEANINGS` / `CONTROL_B_MEANINGS` — the only place control-code subtype → meaning mappings are defined. |
| `script_unit` | Segments a decoded buffer into `ScriptUnit` objects with explicit, gapless word-offset boundaries (`unit_start_offset`, `unit_end_offset`, `next_unit_start_offset`). Adapter/normalization layer only — does not decode or encode itself. |
| `live_extract` | Minimal GDB remote-serial-protocol client (`GdbClient`) plus the live script-buffer capture routine reading from `0x801FE800`. |
| `glyph_atlas` | Reads the glyph pointer table from the executable; `table_entry(code)[1]` is the glyph's real advance width (previously misdocumented as a compressed-byte length — corrected this session). |
| `glyph_char_map` | The static character ↔ glyph-code mapping (`CHAR_TO_CODE`, `char_for_code`, `code_for_char`). Does not require a live connection. |
| `editable_script` | `ScriptSegment`/`EditableScript`, and `to_editable()` — turns a `ScriptDocument` into segments with `original`/`translated` text fields, the layer `script_unit` sits on top of. |
| `editor_state` | `EditorState` + `UnitStatus` enum. In-session unit list, per-unit status/notes/validation/injection-history, and JSON session save/load. No UI, no renderer, no network — pure state. |
| `editor_cli` | Terminal command shell (`cmd.Cmd` subclass) exposing every operator action: `extract`, `edit`, `resolve`, `fit`, `check_layout`, `check_boundary`, `inject_unit`, `inject`, `save`, `load`, and more (full list below). |
| `script_encoder` | `tokenize_translated_text`, `encode_segment`, `encode_script`. Re-tokenizes edited text and re-interleaves control codes at *proportional* positions in the new character stream (the same math `control_position_risk` reads back out for projection). Untouched segments replay byte-for-byte. |
| `font_extension` | Injects a brand-new glyph bitmap into the live font atlas/table for a character with no existing code. |
| `font_workbench` | `classify_char`, `auto_resolve_missing_glyphs` — the substitution/auto-injection policy layered over `font_extension`. |
| `text_fitting` | `fit_text_to_lines`, `pad_line_to_force_wrap`, `center_line`, `fit_text_for_engine` — the current, padding-based word-safe fitting system. This is what Phase 1 must NOT replace or destabilize; `CUSTOM_ENGINE` mode is additive. |
| `control_position_risk` | `FORCED_WRAP_MEANINGS` (`set_flag_d10`, `line_center_calc`, `centered_text_setup`, `alias_of_0x1800`), `STALE_POSITION_MEANINGS` (`pause_flag_a`, `pause_flag_b`), and `project_control_event_positions` — projects where a control code lands in re-encoded text using the same proportional math `script_encoder` uses. |
| `validation` | `ValidationStatus` (`unknown`/`ok`/`overflow`/`missing_glyph`/`control_issue`), `auto_validate` — missing-glyph and control-signature-preservation checks only; fit/overflow is manual-confirm only at this layer. |
| `boundary_validation` | `check_boundary`/`check_chain` — word-count delta and boundary-bookkeeping checks (does editing a unit shift where the next one starts). |
| `layout_validation` | `LayoutValidationStatus` (8 states: `ok`, `pixel_overflow`, `too_many_lines`, `awkward_wrap`, `missing_glyph`, `boundary_risk`, `control_issue`, `style_review_needed`), `check_layout` — composes `validation` + `boundary_validation` with pixel-fit/wrap-quality judgment, returns the single highest-priority issue. |
| `guarded_injection` | `inject_unit_guarded` — the safe operator entry point: runs `check_layout`, hard-blocks on `missing_glyph`/`control_issue`, warns-but-proceeds on the rest, always logs the attempt via `EditorState.record_injection`. |
| `live_injection` | `segment_from_unit`, `encode_units`, `inject_units_live`, `inject_all_live` — rebuilds `ScriptSegment`s from `raw_codes`, re-encodes the WHOLE buffer, writes it back via the GDB `M` packet. Drops `STALE_POSITION_MEANINGS` codes for modified units (see `segment_from_unit`'s own docstring). |

### Other modules present (not named in the master prompt, predate this workbench)

`cdb_codec`, `cdrom`, `cli`, `cluster`, `encoding`, `extractor`, `iso9660`,
`loader`, `render_paths`, `tim` — disc-extraction and image-decoding tooling
from earlier project phases (see `README.md`). Unrelated to the live-injection
pipeline; out of scope for this work and not touched by it.

## Public integration points

**`editor_cli.EditorCLI` commands** (the operator-facing surface):
`list`, `show`, `boundary`, `check_boundary`, `check_chain`, `fit`,
`check_layout`, `flag_style`, `filter`, `edit`, `reset`/`revert`, `note`,
`extract`, `validate`, `confirm`, `glyphs`, `audit`, `resolve`, `glyphlog`,
`inject_unit`, `history`, `inject`, `types`, `extract_type`, `save`, `load`,
`quit`.

**Direct-import entry points** other code (and any new engine layer) would
call: `EditorState.load_units/edit/get/search/save_session/load_session`,
`text_fitting.fit_text_for_engine`, `layout_validation.check_layout`,
`guarded_injection.inject_unit_guarded`, `live_injection.inject_all_live`,
`script_unit.extract_live_script_units`.

## Current editor-to-injection flow

```
extract_live_script_units()          [script_unit + live_extract]
        -> EditorState.load_units()
        -> operator: edit / resolve / fit           [editor_cli -> font_workbench, text_fitting]
        -> check_layout()                            [layout_validation]
        -> inject_unit_guarded() / inject_all_live()  [guarded_injection -> live_injection -> script_encoder]
        -> EditorState.record_injection()
        -> EditorState.save_session()
```

`ScriptUnit`'s identity today is entirely tied to a live capture: `id` is
`f"{scene_id}_line_{index:02d}"`, and `ram_address` is derived from
`live_extract.SCRIPT_BUF_ADDR` (`0x801FE800`) plus the unit's own word offset.
There is no disc-resource identifier yet — the master prompt's `LIVE_RAM` /
`DISC_RESOURCE` source-layer split does not exist. `source` is currently
always the literal string `"live_ram"` (`"disk"` is noted in `script_unit.py`
as "future scope, not implemented").

## Session schema today (no version field)

`EditorState.to_session_dict()` currently emits:
```json
{"units": [...], "status": {...}, "notes": {...}, "validation": {...}, "injection_log": [...]}
```
`ScriptUnit.to_dict()` emits exactly its 12 dataclass fields (`id`, `source`,
`ram_address`, `unit_start_offset`, `unit_end_offset`,
`next_unit_start_offset`, `raw_codes`, `control_events`, `original_text`,
`edited_text`, `layout_constraints`, `text_type`, `glyphs_used`,
`missing_glyphs`). Neither dict has a `schema_version` key today — Phase 1
adds one and must keep old, unversioned session files loadable.

## Known control-code meanings (input to the Phase 1 policy table)

From `script_decoder.CONTROL_A_MEANINGS` / `CONTROL_B_MEANINGS` — 30 named
subtypes total across families A and B, plus unnamed ones that decode with
`meaning=None`. Already-classified-by-behavior subset (from this session's
live investigation, encoded today as `control_position_risk`'s two sets):

- **Forces an unconditional line break** (`FORCED_WRAP_MEANINGS`):
  `set_flag_d10`, `line_center_calc`, `centered_text_setup`,
  `alias_of_0x1800`.
- **Positions using unpredictable leftover state** (`STALE_POSITION_MEANINGS`):
  `pause_flag_a`, `pause_flag_b`.
- Everything else currently has no special-cased runtime behavior recorded
  and is preserved verbatim by `script_encoder`/`live_injection` today.

## Components that must remain unchanged for this work

Per the master prompt's non-negotiable architectural rule, `HOST_FITTED` mode
is exactly today's pipeline, unmodified:
`script_decoder`, `script_unit`, `live_extract`, `glyph_atlas`,
`glyph_char_map`, `editable_script`, `script_encoder`, `font_extension`,
`font_workbench`, `text_fitting`, `control_position_risk`, `validation`,
`boundary_validation`, `layout_validation`, `guarded_injection`,
`live_injection`. `editor_state` and `editor_cli` may gain new fields/commands
in later phases but their existing methods and session format must keep
working exactly as documented above.

## Confirmed still working after this baseline check

- 161/161 tests pass.
- `EditorState.save_session`/`load_session` round-trips the current
  (unversioned) schema correctly — verified by `tests/test_editor_state.py`
  and `tests/test_validation.py`'s session-roundtrip tests, both in the
  passing set above.
- No live emulator connection was required for this baseline check (pure
  static/test inspection) — the live GDB pipeline's own reliability was
  already re-confirmed multiple times earlier this session and is not
  re-verified again here to avoid an unnecessary live round-trip.
