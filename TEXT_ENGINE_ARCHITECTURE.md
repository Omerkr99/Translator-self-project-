# Alternative Text Engine — Architecture (Phase 1)

Tracks the master prompt's "Alternative In-Game Text Engine and
Editor-Controlled Rendering Pipeline" work. This document covers only what
Phase 1 actually built: new data models, with no emulator patching and no
change to the existing pipeline's behavior. See `BASELINE_REPORT.md` for
the state everything here was built on top of.

## The three-way split the whole design hangs on

```
text the editor creates          -- ScriptUnit.edited_text (unchanged)
        v
the layout plan the editor defines -- EditorLayoutPlan (new, Phase 1)
        v
the mechanism in the game that executes it -- CUSTOM_ENGINE renderer (NOT built yet)
```

Phase 1 built the middle layer's data shape only. There is no game-side
consumer for it yet — selecting `RenderMode.CUSTOM_ENGINE` on a unit today
just records the intent; `HOST_FITTED` (today's real, reliable pipeline)
is what actually renders until a later phase builds the rest.

## New modules

- **`gcrts.render_mode`** — `RenderMode` (`ORIGINAL` / `HOST_FITTED` /
  `CUSTOM_ENGINE`), `RuntimePatchStatus` (the 6 named milestones from the
  master prompt's injection-modes section), and `RuntimePatchState` (one
  independent boolean per milestone — a text buffer can be injected with
  no engine patch installed at all, which a single enum couldn't represent).
- **`gcrts.control_policy`** — `ControlPolicy` (`PRESERVE` / `TRANSFORM` /
  `HOST_ONLY` / `ENGINE_ONLY` / `DROP_WITH_WARNING` / `UNRESOLVED`) and
  `CONTROL_POLICY_TABLE`, a record for every named control-code meaning in
  `gcrts.script_decoder`. Only two groups have a real behavioral finding
  behind them (the forced-wrap group → `TRANSFORM`, the stale-position
  group → `DROP_WITH_WARNING`, matching what `gcrts.live_injection`
  already does); everything else is `UNRESOLVED` — a name from the
  decompile is not a confirmed behavior, and this project's own strict
  rule is not to claim otherwise without live evidence.
- **`gcrts.editor_layout_plan`** — `EditorLayoutPlan`, `LayoutLine`,
  `LayoutPlanValidation`, plus the `LayoutAlignment` / `LayoutMode` /
  `PageTransition` vocabularies. Deliberately NOT built on
  `gcrts.layout_validation.LayoutReport` — that module reports a verdict
  on HOST_FITTED's padding output (single highest-priority status out of
  8); this is the editor's own intended layout (explicit lines, positions,
  a multi-flag validation summary) — different information, kept separate
  rather than forced into one shape.

## `ScriptUnit` changes (backward compatible)

Four new fields, all with defaults, appended after the existing ones:
`render_mode` (default `HOST_FITTED`), `layout_plan` (default `None`),
`runtime_patch_status` (default all-`False`), `preview_status` (default
`"unknown"`). Every existing construction call site — `unit_from_segment`,
every test's hand-built `ScriptUnit(...)` — works unchanged, since Python
only requires trailing defaulted dataclass fields to have defaults, not
that callers pass them.

`to_dict()`/`from_dict()` serialize/deserialize all four; `from_dict()`
uses `.get()` with the same defaults for each, so a dict from before these
fields existed loads exactly as if the unit had always been `HOST_FITTED`
with no plan — verified by
`test_a_dict_from_before_these_fields_existed_still_loads_with_defaults`.

## `EditorState` changes (backward compatible)

Added `CURRENT_SCHEMA_VERSION = 2` and a `"schema_version"` key in
`to_session_dict()`. `load_session()` defaults a missing key to `1` — there
is no structural migration to perform between the two versions, since
`ScriptUnit.from_dict()`'s own field-level defaults already make an
unversioned file load correctly. The version constant exists so a future
version that DOES need a real migration step has something to branch on.

## What Phase 1 explicitly did NOT do

Per the master prompt's non-negotiable rule and Phase 1's own definition of
done:

- No MIPS patching, no hook installation, no code-cave search.
- No change to `gcrts.text_fitting`, `gcrts.live_injection`,
  `gcrts.script_encoder`, or any other module in `BASELINE_REPORT.md`'s
  "must remain unchanged" list.
- No automatic layout-plan generation — `EditorLayoutPlan.lines` is
  populated by hand in tests today; an automatic planner (reusing
  `gcrts.text_fitting`'s word-segmentation logic per the master prompt's
  section 9) is later-phase scope.
- No editor UI changes — `gcrts.editor_cli` has no new commands yet.

## Test coverage added

24 new tests across `tests/test_render_mode.py`,
`tests/test_control_policy.py`, `tests/test_editor_layout_plan.py`, plus
additions to `tests/test_script_unit.py` (5 new tests covering defaults,
roundtrip, and old-dict compatibility) and `tests/test_editor_state.py` (2
new tests covering `schema_version` and old-session-file loading). 185
total, all passing (161 baseline + 24 new).

## Phase 2 — the binary layout descriptor

Built `gcrts.layout_descriptor` (`encode_layout_descriptor`/
`decode_layout_descriptor`) implementing the format specified in
`CUSTOM_LAYOUT_DESCRIPTOR.md` — a fixed 18-byte header, fixed 10-byte line
records (addressable at `HEADER_SIZE + i * 10`, no variable-length walk
needed), and a trailing character-code stream reusing
`gcrts.script_encoder.tokenize_translated_text`'s exact 16-bit glyph
codes, so a future MIPS renderer can hand a line's slice straight to the
game's existing glyph-blit routine instead of needing a second text
representation. Every field little-endian and at an even byte offset
(both verified by a dedicated test) — real MIPS load-instruction
constraints, not style.

Three defensive bounds (`MAX_LINES=64`, `MAX_LINE_CHARS=256`,
`MAX_TOTAL_CHARS=4096`) are enforced by BOTH the encoder (rejects before
producing bytes) and the decoder (rejects a header's claims before
trusting them against the actual buffer given) — a corrupt or foreign
buffer can never cause an out-of-bounds read, and an oversized plan is
never silently truncated, always a raised `DescriptorValidationError`.

Still pure Python. No MIPS code, no code-cave search, no emulator
interaction — every function in `gcrts.layout_descriptor` is a pure
function of its input bytes/plan.

15 new tests in `tests/test_layout_descriptor.py`: two golden tests
asserting the EXACT expected byte layout (not just round-trip) for a
known input against real, confirmed glyph codes; round-trip tests; and
one test per validation rule in the spec's "validation a decoder must
perform" list (bad magic, wrong version, truncated buffer, nonzero
reserved bytes, each of the three bounds). 200 total tests, all passing
(185 after Phase 1 + 15 new).

## Phase 3 — editor integration

This project's "Text Editor" is `gcrts.editor_cli.EditorCLI`, a terminal
command shell over `gcrts.editor_state.EditorState` — there is no separate
GUI in this codebase, so "editor integration" means integrating the Phase
1/2 models into those two existing modules, matching `editor_cli.py`'s own
stated design ("no business logic lives in this module... a thin renderer
over EditorState").

**`gcrts.layout_plan_builder`** (`build_auto_layout_plan`) — builds a
starting `CUSTOM_ENGINE` plan from a unit's `edited_text`, reusing
`gcrts.text_fitting.fit_text_to_lines` for word segmentation (per the
master prompt's section 9: don't re-implement tokenization) and assigning
each resulting line an explicit `(x, base_y + i*line_height)` position and
character-index span computed by walking `edited_text` in order. `base_x
= 10` reuses the one confirmed wrap-algorithm constant; `base_y`/
`line_height` are explicitly documented as NOT confirmed game constants —
reasonable starting defaults, not measured facts.

**`gcrts.layout_preview`** (`LinePreview`, `LayoutPreview`, `build_preview`)
— the "preview data model" the master prompt's Phase 3 asks for, kept
deliberately separate from an actual renderer (that's Phase 4's "Software
preview" scope): computes per-line measured pixel width (reusing
`gcrts.layout_validation.measure_pixel_width`), overflow against each
line's own budget, whether the plan exceeds the confirmed
`MAX_VISIBLE_LINES=4`, and missing glyphs (reusing
`gcrts.font_workbench.classify_char`) — all pure data, no drawing.

**`EditorLayoutPlan` manual editing** — `add_line`/`remove_line`/
`update_line` methods, matching `EditorState`'s own mutate-in-place style.

**`EditorState` additions** — `set_render_mode`, `get_layout_plan`,
`set_layout_plan`. Setting a layout plan does NOT change render_mode and
vice versa — an operator can draft/edit a `CUSTOM_ENGINE` plan while a unit
still renders `HOST_FITTED` live, matching the master prompt's fallback
requirement (a plan that fails validation shouldn't lose the draft that
failed).

**`EditorCLI` commands** — `layout_mode`, `layout_auto`, `layout_show`,
`layout_add_line`, `layout_update_line`, `layout_remove_line`,
`layout_preview`. Each is a thin wrapper printing a state-model result,
consistent with every other command in this file.

**Persistence** — already worked via Phase 1's `ScriptUnit.to_dict`/
`from_dict`, which already serializes `layout_plan`; this phase added an
explicit end-to-end test (`test_layout_plan_persists_through_do_save_and_do_load`
and `test_layout_plan_survives_a_full_session_save_load_roundtrip`)
proving a plan built via `layout_auto`, saved via `do_save`, and reloaded
via `do_load` comes back intact.

Still no MIPS code, no code-cave search, no emulator interaction.
`HOST_FITTED` remains what actually renders live; `layout_mode` only
changes what a unit is MARKED as wanting, since no `CUSTOM_ENGINE`
consumer exists yet.

30 new tests across `tests/test_layout_plan_builder.py` (5),
`tests/test_layout_preview.py` (6), `tests/test_editor_layout_plan.py`
(+8 for the new editing methods), `tests/test_editor_state.py` (+4),
and `tests/test_editor_cli.py` (+9, including the two persistence
round-trips). 230 total, all passing (200 after Phase 2 + 30 new).

## Phase 4 — the software preview renderer

**`gcrts.layout_software_preview`** (`render_layout_plan`,
`render_layout_plan_to_file`) — actually draws pixels, using Pillow
(already a declared project dependency, already in active use in
`gcrts.font_extension`). Consumes Phase 3's `layout_preview.build_preview`
for which lines overflow and which characters have no known glyph, and
`gcrts.glyph_atlas.GlyphAtlas.decode_glyph`/`glyph_to_pixels` for the
REAL glyph bitmaps (not a substitute font). Draws, per line: the real
glyph pixels at the correct alignment-adjusted position, a textbox-bounds
outline (red if that line overflows its own budget), a baseline, and a
red marker for any character with no known glyph code.

Reuses the project's own CONFIRMED palette convention
(`gcrts.font_extension.FONT_BACKGROUND_VALUE=4`/`FONT_INK_VALUE=6`, live-
confirmed by inspecting a real glyph's pixel histogram — see NOTES.md's
"Phase 6 CONFIRMED LIVE" section) instead of assuming the naive
0=background/15=ink convention that section already found to be wrong.
Values between the two (or beyond) blend linearly toward ink -- a
rendering choice for antialiasing edges, not a claim about the exact
intended ramp, since only the two endpoints are actually confirmed.

**A real bug this phase's own tests caught**: the first draft drew each
line's bounds/baseline/missing-glyph markers BEFORE that line's glyphs,
so a solid glyph covering a line's top-left corner silently painted over
the overflow-warning outline there — overflow become invisible exactly
when it mattered most (a glyph actually present at that spot). Fixed by
drawing glyphs first, indicators on top, always visible regardless of
glyph content.

**Known, documented limitation**: this project has never captured the
live, per-chapter glyph-bitmap resource blob `GlyphAtlas.decode_glyph`
needs to resolve a REAL glyph's compressed pixel data (see
`glyph_atlas.py`'s own module docstring — the width TABLE lives in the
static EXE, but the compressed bitmap DATA it points to lives in a
separate, dynamically-loaded RAM blob observed live at `0x8001a200`).
`EditorCLI.do_layout_render` loads only the static EXE, matching every
other `--pixel`-flavored command in this file — so today it will render
every character as a missing-glyph marker, which is the honest, correct
result given what's actually available, not a silent fallback pretending
otherwise. Wiring in a live capture of that blob is unstarted work, not
assumed to be trivial.

Tests use a deterministic fake atlas (`decode_glyph` returns a synthetic
all-background or all-ink 16×16 cell) rather than requiring a live
emulator connection, matching this project's existing `_fake_atlas` test
pattern from `test_layout_validation.py`. 10 new tests across
`tests/test_layout_software_preview.py` (8) and `tests/test_editor_cli.py`
(+2, including a real PNG round-trip through a temp file). 240 total, all
passing (230 after Phase 3 + 10 new).

## Phase 5 — memory research

Full findings in `MEMORY_MAP_FINDINGS.md`, consolidating the earlier
(pre-master-prompt) investigation from NOTES.md with new work done
specifically for this phase. Summary:

- **Static executable slack** (13.1): two candidates already tested live
  with a marker-write methodology, both confirmed actively used — no
  change from the earlier investigation.
- **Stack headroom** (13.2): read the live register set via a single safe
  GDB `g` packet (no breakpoint, no freeze risk) and confirmed
  `$sp=0x801ffd90` sits ~623 bytes below the top of RAM. Sampled again
  after the operator advanced dialogue: **identical value** — which is
  itself the finding, not a null result. Point-in-time sampling between
  human actions can only ever catch the game's steady-state idle depth;
  whatever deeper stack usage happens during a few milliseconds of actual
  rendering is invisible to this technique. Measuring real peak depth
  would need a breakpoint at the exact instant of deepest recursion,
  reintroducing the documented freeze risk for a technique that already
  failed to produce data four times earlier this project. Not attempted
  again. Flagged one real safety observation regardless: the script
  buffer sits only ~7.3 KB below observed idle `$sp`.
- **Overlay-specific memory** (13.3): confirmed to be a REAL concern, not
  just a theoretical caution — this game has at least 10 differently-sized
  overlay executables (`CAP0`–`CAP4`, `CAPX`, plus character-named ones
  matching the 5 narrative call sites found earlier). Both tested memory
  candidates were only ever verified against CAP0.EXE specifically.
- **13.4–13.6** (reusable buffers, dev-only external patching, disc-level
  relocation): documented, none newly investigated — see the findings
  doc for why each is either already covered or correctly out of scope
  for this phase.

**No memory region is confirmed safe for a permanent code cave.** Per the
master prompt's own instruction, Phase 6 (MIPS patch design) should not
proceed to writing an actual hook/dispatcher until this gap closes —
either a genuinely free region is found (a wider scan, tested per-overlay)
or a different strategy is chosen (e.g. development-only external
patching, scoped to "verified safe for this run only"). Still no MIPS
code, still no emulator patching in this codebase itself.

## Phase 6 — MIPS patch design (design only, no bytes written)

Full plan in `MIPS_PATCH_PLAN.md`. Proceeded with design work despite
Phase 5's open memory question, since design (hook site, register plan,
pseudocode) doesn't require an install address to reason about correctly
— only writing real bytes does, and nothing was written.

**A live re-verification caught a real bug in the plan before it became
a live crash.** The static-analysis hook site from the earlier
blast-radius investigation (`jal 0x8004a370` at `0x80048e50`) was
re-checked against the actually-running session with a single safe
memory read — and didn't match: the live JAL sits at `0x80048e48` and
targets a completely different function (`0x80044d98`). Confirms Phase
5's overlay-variance concern (13.3) extends to CODE addresses, not just
data. The wrap function's OWN address (`0x8004a370`) checked out exactly
as expected, though — leading to hooking the function's entry rather
than any specific caller.

**A second real bug caught by the same review**: naively patching
`FUN_8004a370`'s first instruction with a jump would silently corrupt the
caller's `$s0` register, because a MIPS jump's delay slot (the next
instruction, `addu $s0,$a0,$zero`) would still run — but the instruction
it depended on (`sw $s0,...`, saving the caller's original value) would
never execute, since that's the one being overwritten. Corrected hook
site: the SECOND instruction (`0x8004a374`), where the delay slot
(`sw $ra,...`) has no such dependency.

**Also fixed, surfaced by this same design review**: `gcrts.layout_descriptor`
(Phase 2) stored each line's raw, pre-alignment `x` with no per-line width
budget in the binary format — meaning a future MIPS parser reading only
those bytes would have nothing to center or right-align WITHIN.
`encode_layout_descriptor` now resolves alignment into a final `x` once,
at encode time (optional `atlas` parameter, same fallback convention as
every other function in this project), so the MIPS parser never needs
alignment math at all. `CUSTOM_LAYOUT_DESCRIPTOR.md` updated to match; 3
new tests confirm CENTER/RIGHT/LEFT all resolve correctly. 243 total
tests, all passing (240 after Phase 4 + 3 new).

Dispatcher and descriptor-parser pseudocode, the full register/stack
plan, and what's still explicitly left open (how a descriptor gets
associated with a specific unit; full register liveness beyond the three
registers directly verified; per-overlay hook-address verification) are
all in `MIPS_PATCH_PLAN.md` — not repeated here.

## Phase 7 — installed live, verified working (first real code patch)

Full account in `MIPS_PATCH_PLAN.md`'s "Phase 7" section. Summary: a
wider memory re-scan found a much larger candidate than Phase 5's two
failures (`0x801a0000`, 30KB of zeros), confirmed safe across two
independent rounds of real gameplay using the same marker-write
methodology. A minimal 12-byte "always fallback" stub was written there,
and the 4-byte hook patch redirecting `FUN_8004a370`'s entry to it was
installed at `0x8004a374` — the first time this project has changed live
game CODE rather than data. Original bytes saved to a standalone restore
script before writing, per this project's established practice.

**Verified live**: the operator advanced dialogue on a real, new scene
immediately after the patch, and it rendered with zero visible
difference from unpatched behavior. This confirms every register-liveness
and delay-slot assumption in Phase 6's design held up against real
execution, not just careful reasoning.

**What's NOT yet proven**: only the fallback path was exercised — the
stub doesn't look for a real descriptor yet, so the dispatcher's actual
branch logic, the descriptor parser, and `find_descriptor_for()` (still
undesigned) remain untested. This is a mechanism proof, not a working
feature yet.

**This remains a per-session finding**, not a permanent one — the memory
region is confirmed safe for THIS run only, not re-verified after a
reload/restart or against any other overlay, exactly matching the master
prompt's development-only framing (13.5), not a claim of having solved
Phase 5's open question generally.

## Phase 7 correction, Phase 8, and Phase 9 — see `MIPS_PATCH_PLAN.md`

Everything past this point happened in `MIPS_PATCH_PLAN.md` rather than
here, per this file's own rule (add sections, don't rewrite earlier
ones) — this section is a pointer, not a duplicate:

- **Phase 7 correction**: the "verified working" claim above turned out
  to be a false positive — the hook was never actually shown to fire,
  only shown not to break anything if it never fired. Found while
  debugging why an extended, branch-on-real-descriptor stub's marker
  never set; root-caused via a canary at the function's true entry, then
  a save-state reload that directly confirmed real overlay/layout
  variance (a previously-safe scratch region became fully occupied, and
  a structurally-similar function shifted 4 bytes with a bigger frame).
  A fresh install in the new state proved the mechanism genuinely works:
  canary fired within seconds, and the full branch-on-descriptor logic
  correctly distinguished `pointer=0` (fallback, marker stays 0) from a
  real valid descriptor (marker set to 1) — both live, both with zero
  visible regression.
- **Phase 8**: built the per-executable profile framework
  (`gcrts/mips_patch_profile.py`) the master prompt asks for, with one
  profile live-confirmed under an honest placeholder name (executable
  identity was never independently determined). Live verification of
  the actual five narrative executables and the CAP0-4/CAPX group is
  explicitly not done — it requires reaching each scenario in-game.
- **Phase 9**: built the software-only groundwork (`gcrts/
  layout_descriptor_injection.py`) connecting an `EditorLayoutPlan` to a
  live-injectable descriptor + pointer, against a live-confirmed
  profile. The live custom renderer — the part that would actually draw
  glyphs at editor-specified positions — remains explicitly deferred,
  per the same "Safe version now" decision made during Phase 7. A real
  open design question was surfaced (not resolved): whether a custom
  renderer intercepts per-character like today's hook, or takes over the
  master render loop (`FUN_800481b0`) wholesale for a textbox's duration
  — see `MIPS_PATCH_PLAN.md`'s Phase 9 section for the full reasoning.

Do not start further phase work by editing this document's earlier
phase sections; add a new section instead so this file keeps recording
what was true when each phase shipped.
