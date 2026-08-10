# Text Position Trace Log

One row per key runtime event captured live this session. All captures
against the `UNIDENTIFIED_SESSION_2026-07-27` profile (shifted layout,
`FUN_8004a370` entry at `0x8004a370`) — see `mips_patch_profiles.json`.
Executable identity beyond that placeholder name was never independently
determined (no fingerprinting against a named `CAP*.EXE`/character
executable was run this session).

## Legend

- `source` = record field this session traced as the candidate producer
- `result` = CONFIRMED (live-modification-tested) / RULED_OUT / OBSERVED (not yet modification-tested)
- `confidence` = HIGH (multiple confirming captures + modification test) / MEDIUM (disassembly + one capture) / LOW (single observation)

## Event set A — first 8 characters of a fresh line, wrap-function cursor (`FUN_8004a370` common exit, `0x8004a9d4`)

| glyph_idx | call_index (`DAT_800a4cd8`) | dest_x (`+8`) | dest_y (`+0xA`) | source | last_writer | result | confidence |
|---|---|---|---|---|---|---|---|
| 0 | 0 | 10 | 152 | `+8`/`+0xA` | `FUN_8004a370` @ `0x8004a50c` (normal case) | OBSERVED | HIGH |
| 1 | 1 | 26 | 152 | `+8`/`+0xA` | `FUN_8004a370` @ `0x8004a50c` | OBSERVED | HIGH |
| 2 | 2 | 38 | 152 | `+8`/`+0xA` | `FUN_8004a370` @ `0x8004a50c` | OBSERVED | HIGH |
| 3 | 3 | 52 | 152 | `+8`/`+0xA` | `FUN_8004a370` @ `0x8004a50c` | OBSERVED | HIGH |
| 4 | 4 | 64 | 152 | `+8`/`+0xA` | `FUN_8004a370` @ `0x8004a50c` | OBSERVED | HIGH |
| 5 | 5 | 78 | 152 | `+8`/`+0xA` | `FUN_8004a370` @ `0x8004a50c` | OBSERVED | HIGH |
| 6 | 6 | 92 | 152 | `+8`/`+0xA` | `FUN_8004a370` @ `0x8004a50c` | OBSERVED | HIGH |
| 7 | 7 | 106 | 152 | `+8`/`+0xA` | `FUN_8004a370` @ `0x8004a50c` | OBSERVED | HIGH |

X deltas: 16, 12, 14, 12, 14, 14, 12 — real, varying proportional glyph
widths. Y constant within the line, as expected.

**Live modification test on this field**: broke at `0x8004a9d4` (idx=0),
changed `+8` from 10 to 220, resumed, screenshotted. **No visible
change** in rendered output.

Row: | idx=0 | `+8`=10→220 | — | `+8` | `FUN_8004a370` | **RULED_OUT** | HIGH

## Event set B — one sample deep into a line (mid-session, before the 8-glyph set above was captured)

| glyph_idx | call_index | dest_x (`+8`) | dest_y (`+0xA`) | blit_raw (`+0`,`+2`) | blit_shifted | result | confidence |
|---|---|---|---|---|---|---|---|
| 26 | 43 | 64 | 190 | 176, 32 | 44, 8 | OBSERVED | MEDIUM |

Solved formula: `param_3[8]=16` ⇒ `ratio=16` ⇒ `43 mod 16=11` (×16=176 ✓),
`43 div 16=2` (×16=32 ✓). Confirms the same fixed-16-cell-grid pattern
seen in event set C below, one row further along.

## Event set C — first 10 characters at the GPU-upload call site (`0x8004aab0`, `jal 0x800786b8`)

| glyph_idx | call_index | dest_rect (x,y,w,h) | record `+0` | source | last_writer | result | confidence |
|---|---|---|---|---|---|---|---|
| 0 | 0 | 320, 256, 4, 16 | 0 | `+0` | `FUN_8004a8c0` @ `0x8004a994` | OBSERVED | HIGH |
| 1 | 1 | 324, 256, 4, 16 | 16 | `+0` | `FUN_8004a8c0` | OBSERVED | HIGH |
| 2 | 2 | 328, 256, 4, 16 | 32 | `+0` | `FUN_8004a8c0` | OBSERVED | HIGH |
| 3 | 3 | 332, 256, 4, 16 | 48 | `+0` | `FUN_8004a8c0` | OBSERVED | HIGH |
| 4 | 4 | 336, 256, 4, 16 | 64 | `+0` | `FUN_8004a8c0` | OBSERVED | HIGH |
| 5 | 5 | 340, 256, 4, 16 | 80 | `+0` | `FUN_8004a8c0` | OBSERVED | HIGH |
| 6 | 6 | 344, 256, 4, 16 | 96 | `+0` | `FUN_8004a8c0` | OBSERVED | HIGH |
| 7 | 7 | 348, 256, 4, 16 | 112 | `+0` | `FUN_8004a8c0` | OBSERVED | HIGH |
| 8 | 8 | 352, 256, 4, 16 | 128 | `+0` | `FUN_8004a8c0` | OBSERVED | HIGH |
| 9 | 9 | 356, 256, 4, 16 | 144 | `+0` | `FUN_8004a8c0` | OBSERVED | HIGH |

`dest_rect.x` advances by exactly +4 every character (matching the
fixed cell width, `w=4`) regardless of actual glyph identity or width —
the signature of a fixed-stride cache/atlas grid, not proportional
on-screen text placement. `y` and `w`/`h` constant throughout this
8-row window (row wraps only occur past 16 cells, per the formula
solved in event set B).

**Live modification test on this field** (corrected for timing — see
`MIPS_PATCH_PLAN.md`'s "Empirical confirmation" section for the full
account of the first, mistimed attempt): broke at `FUN_8004aa08`'s
entry (`0x8004aa08`, BEFORE `+0`/`+2` are read), changed `+0` from 192
to 800, resumed, screenshotted.

Row: | idx=0 | `+0`=192→800 | — | `+0` | `FUN_8004a8c0` | **partially CONFIRMED** (produces a real visible artifact — a stray disconnected dot) but **RULED_OUT as the primary live-text mechanism** (the actual dialogue sentence rendered with zero visible disruption) | HIGH

## Event set D — indirect-call target resolution and debug-print confirmation

| step | value | evidence | result | confidence |
|---|---|---|---|---|
| function pointer at `0x8009d448` | `0x80077f68` | live memory read | RESOLVED | HIGH |
| `0x80077f68` disassembly | `addiu $t2,zero,0xa0; jr $t2; addiu $t1,zero,0x3f` | live disassembly | standard PS1 BIOS A0-call trampoline (function `0x3f`) | HIGH |
| first argument to the call site | `0x80046e90` (fixed address) | live disassembly of caller (`0x8007ad8c`-`0x8007ae24`) | fixed, not computed — format-string shape | HIGH |
| content at `0x80046e90` | `"tpage: (%d,%d,%d,%d)\n   clut: (%d,%d)\n  clip (%3d,%3d)-(...)"` | live memory read | **CONFIRMED debug printf logging GPU attributes** | HIGH |

**Result: this indirect-call chain is a debug-mode logging path, not a
primitive-submission mechanism.** Resolved via live data (function
pointer value + string content), not inferred from bit-packing shape
alone, satisfying the task's explicit bar against weaker forms of
evidence.

## Event set E — double-buffering hypothesis test

| capture | t (ms) | dialogue text state | anomaly |
|---|---|---|---|
| 0 | 0 | "ミカ：窓の外・・・、なんか動いた・・・" (normal) | none |
| 1 | 180 | same, normal | none |
| 2 | 360 | same, normal | none |
| 3 | 540 | same, normal | none |
| 4 | 720 | textbox cleared (natural game progression) | none |

Row: | `+0`=48→800, idx=9 | screen-visible over 5 captures / 800ms | `+0` | `FUN_8004a8c0` | **RULED_OUT (re-confirmed)** — no delayed appearance supporting a buffer-swap explanation | HIGH

## Event set F — mode-aware frame capture (2 rounds, 40 hits total)

Full mode table and evidence in `FRAME_RENDER_MODES.md`. Summary:

| mode | flags | hits (of 40) | confidence |
|---|---|---|---|
| WIDTH_MODE (0) | `0x02` | 7 | HIGH |
| RESET_MODE (1) | `0x12` | 26 | HIGH |
| NO_FRAME_CALL | `0x04`,`0x08`,`0x20` | 7 | HIGH |
| Y_COLLECTION_MODE (3) | bit `0x40` set | **0** | MEDIUM (disassembly only — not live-caught) |

Round 2 specifically targeted a live-confirmed 4-full-visible-line
textbox (screenshot: "その子の呼び出し方!／逸島センパイの方が／マイナ
ーなウワサ知ってるなんて／ちょっとくやしーよ") advanced past its
boundary — still zero mode-3 hits. This is the current, explicit
frontier: catching mode 3 live is required before the Y-value-list
consumer can be traced forward (task Step 5) or live-modification-
tested (task Step 6).

## Open / not yet captured

- **RESOLVED this round, superseding the note above**: the indirect
  call through the function-pointer table at `0x8009d448` was fully
  traced and is a debug-mode printf logging GPU tpage/clut/clip
  attributes (see event set D) — NOT a primitive-submission mechanism.
  `FUN_8004aae8`/`FUN_8007ad74`/`FUN_8007acdc` are confirmed
  attribute-packing/logging helpers, not the screen-destination writer.
  The double-buffering alternative this raised was tested (event set
  E) and not supported. **The real screen-destination writer remains
  unidentified** — the search must now broaden beyond this call chain
  (see `INDIRECT_RENDER_TARGETS.md`'s "Remaining next experiment":
  scan for other callers of `0x800786b8`).
- First-glyph-vs-second-glyph differential trace (task Step 3): the
  event-set-A data above answers this for the wrap function's cursor
  (proportional advance, not a shared recomputed base) — the SAME
  comparison for whatever function turns out to be the real
  screen-position source has not been done, since that source isn't
  identified yet.
- Before/after line-break trace (task Step 4): not captured this
  session — the wrap-reset formula was reverse-engineered from static
  disassembly in `MIPS_PATCH_PLAN.md` (`bVar1+sVar4+param_2[0]`) but not
  re-confirmed via live breakpoint capture at a real wrap boundary.
- Differential trace between layout modes (task Step 5): not attempted
  — would require reaching a centered/differently-aligned textbox
  in-game, not encountered this session.

## Event set G — chapter-1 profile, full mode-dispatch round (later session)

Against the independently-re-derived chapter-1 profile (decoder entry
`0x800398A4`, NOT the `UNIDENTIFIED_SESSION_2026-07-27` profile the
sets above were captured against — see `MASTER_RENDER_MODE_MAP.md`'s
"Layout drift log" for the full chain of profile transitions this
session went through). Full detail in `MASTER_RENDER_MODE_MAP.md`/
`VISIBLE_DIALOGUE_COMPOSITION_PATH.md`; summary rows:

| candidate | field | captured value(s) | modified value | result |
|---|---|---|---|---|
| candidate A (`0x8003AFFC`) | record `+0`/`+2` | cache-shaped | extreme | RULED OUT (isolated artifact, real text unaffected) |
| candidate C (`0x8003B144`) | assembled rect | `X=328,Y=320,W=4,H=16` | X=200 | RULED OUT (no visible change) |
| mode 1 write (`0x8003A7D0`) | record `+8`/`+0xA` | `(249,191)`, `(258,172)` | X=10 (×2) | RULED OUT (confirmed fresh at write time, no visible change) |
| mode 2 collection (`0x8003A884`) | dedicated Y array `0x800A3A0C` | `152`, `171` (alternating, real) | Y=5 | RULED OUT (confirmed still-active at screenshot time, no visible change) |
| candidate D (`0x8003AAAC`) | record `+8`/`+0xA` | `X=13, Y=152` | X=10 | **INCONCLUSIVE** — reverted before observable; recomputed faster than test methodology |

`Y=152` was independently captured three separate times this round
(mode 1's second sample, mode 2's collection, and candidate D) —
matching this exact document's own event set A `Y=152` constant from
the ORIGINAL chapter-0 investigation. This is strong convergent
evidence that `152` is a genuine, stable on-screen Y value for this
specific line/textbox, even though no single write site tested this
round has been confirmed as what the renderer actually consumes to
draw it.

## Event set H: candidate D's source traced to a static template, causality still unconfirmed

Follow-up round traced candidate D's own source (`0x800A38D4`/`+2`) to
a static compiled-in template at `0x80090AB0` (X at `+0xC`=10, Y at
`+0xE`=152 — a **fourth** independent appearance of the `152` constant,
this time as a static value rather than a live-captured one). Two
live-modification rounds gave contradictory results:

| round | delta | source→copy propagation | candidate-D destination result |
|---|---|---|---|
| 1 | 10→200 | confirmed within 3s | 203 (=200+3, matches documented offset) |
| 2 | 10→60 | confirmed within 9s | passed through unrelated value 38, settled at exactly 60 (offset did NOT reproduce) |

Root cause: the index counter (`0x800A39DC`) advanced from a low value
to 26 during the test windows, proving the destination slot
(`record[0]+8`) is shared and continuously overwritten by unrelated,
ordinary per-character gameplay during the multi-second windows these
tests require. A tight chained-breakpoint trial (designed to eliminate
this window entirely) timed out because the copy function does not
fire while the game is idle at a choice menu.

**Update — later round, deterministic same-frame test completed**: a
follow-up session got the emulator back into active dialogue (resuming
a debugger-halted CPU, then simulating a Cross-button press) and
confirmed, via a live landmark check, that a fresh quickload had landed
back in this exact chapter-1 profile. The full chained test (modify
source → verify propagation to `0x800A38D4` → capture the live record
slot → single-step candidate D's store → continue to render →
screenshot before restoring) ran cleanly across two deltas (10→230,
10→160): both showed an **exact** copy into the record (no "+3" offset
— that earlier reading is now understood as a sleep-based-methodology
artifact) but **no visible movement** of the rendered text. **Verdict:
candidate D is RULED OUT.** Full detail in
`VISIBLE_DIALOGUE_COMPOSITION_PATH.md`'s "Deterministic same-frame
round" section. All modifications were restored and verified via
readback.

## Round: two distinct dialogue renderers found; live capture pipeline built and debugged

This round built a proper emulator-state controller
(`scratchpad/estate.py`) and a generation-tracked breakpoint protocol
(see `BREAKPOINT_GENERATION_LOG.md`) specifically to stop treating any
GDB stop notification as a real hit — every stop is now checked
against the current PC before anything is read or written.

**Major new finding**: this game has at least **two distinct
dialogue-box rendering mechanisms**, confirmed by direct evidence, not
inference:
- **Plain conversation boxes** (no inset image): render through the
  already-identified chain — `0x8004500c` → `0x8007b224` (GTE
  quad-builder) → `0x8007b250` (the `swc2` position write). Confirmed
  repeatedly reliable: this exact breakpoint pair produced real,
  validated on-screen candidates multiple times this round alone.
- **Portrait/photo-inset dialogue boxes** (a framed character photo
  shown above the text — the "psychic photo" segments): do **not** use
  this chain at all. Proof: `0x8007b250` was armed **alone** (no
  call-site filter, so any caller would trigger it) during an actively
  progressing portrait-style scene for 60 continuous seconds with zero
  hits. Since that instruction is caller-independent, this rules out
  "different caller, same writer" and confirms a genuinely separate
  renderer that has not yet been located.

**A real bug found and fixed in this round's own tooling**: the
capture script single-stepped only *once* past the `STORE_INSN`
breakpoint before trying to read all four of a `POLY_FT4`'s vertices.
Only the first vertex (`SXY0`) is written by that instruction; the
other three are written by three further instructions
(`0x8007b254`, `0x8007b258`, `0x8007b27c`) later in the same function
that were never stepped past. Every candidate was consequently
rejected as "unreadable" even on runs that hit the breakpoint 500
times. Fixed by single-stepping in a loop until PC passes `0x8007b280`
(just after the fourth vertex write) before reading anything.

**Scene alternation as the practical blocker**: the segment being
tested alternates unpredictably between plain dialogue, portrait-inset
dialogue, and full-screen choice menus (a third UI layer, red
A/B/C options over the same photo backdrop). The identified,
proven-reliable renderer only matches the first of these, so the
capture pipeline's success now depends on catching a live reveal
during a plain-dialogue window specifically — not on any remaining
code-identification uncertainty.

**Correction from a later session** (full detail in
`RENDERER_LIVE_PROOF.md` section 10): the "do not use this chain at
all" conclusion above for portrait/photo-inset and choice-menu text did
not replicate. A later session found the shared writer instruction
(`0x80049088` in that session's addressing — a plain `sh`, distinct
from the `swc2` at `0x8007b250` referenced above) firing reliably for
*both* photo-inset dialogue and a full-screen A/B/C choice menu, using
the exact same primitive-array pattern as ordinary dialogue. Re-testing
`0x8004500c` alone (this section's call site) against that same
content produced zero hits over several minutes, consistent with this
section's finding — the discrepancy is in which renderer covers which
content, not in whether `0x8004500c` fires for that content (it
doesn't, in both sessions' testing). Left unresolved. Separately, that
later session identified the actual reason live edits never
persisted regardless of scene: the primitive array both sessions
targeted is a write-only copy, refreshed every cycle from a source
register (`$s1`); editing that source instead produced the first
successful live visual proof.
