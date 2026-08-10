# Master Render Mode Map

Full per-frame mode dispatch table for the chapter-1 overlay profile
(decoder entry `0x800398A4`, cursor `0x800A39EE`, render-loop dispatch
`0x80038B54` — all independently re-derived and confirmed earlier this
session; see `CURRENT_SYSTEM_STATUS.md` §0 onward). Built from two large
live-capture rounds (362 hits at the render-loop's flags-read point;
16 matching hits at the mode-handler's own entry, correlating flags,
mode, and call site directly) plus full static disassembly of every
reachable branch.

**Important caveat this whole document is written under**: this
project has directly observed the code layout drift *mid-scene*, not
just across quickloads/chapter changes (see "Layout drift log" below).
Every address in this document was validated live at the time it was
captured. Before reusing any of them in a future session, re-validate
with `gcrts.mips_jal_decoder.validate_call_site` first — do not assume
persistence.

## The mode-handler function

**Entry**: `0x8003A6C0`. Prologue: `addiu sp,sp,-0x28` then saves
`s0`-`s4`/`ra`. Reads its 5th (stack) argument — the mode value — as a
byte at `sp+0x38` (post-prologue) / caller's `sp+0x10` (at entry,
before the prologue's own `-0x28` adjustment).

**Arguments observed, identical across every mode**:
- `a0 = 0x800A2AD4` — the main position-records array base.
- `a1 = 0x800A38D4` — a second, per-line/per-textbox base struct.
- `a2 = 0x800A38E4` — a third struct (referenced by mode 2's own
  preamble).
- `a3 = 0x801FFCF8` (varies slightly by call, a per-frame stack address)
  — the "shared buffer" from earlier phases of this investigation.

**Called from exactly three call sites** inside the master render loop:

| Call site (JAL) | Return address | Observed mode(s) | Observed flags |
|---|---|---|---|
| `0x80038c58` | `0x80038c60` | 1 | `0x12` |
| `0x80038ca0` | `0x80038ca8` | 0, 2 | `0x02`, `0x80` |
| `0x80038c00` | `0x80038c08` | (not observed this round — candidate for mode 3, matching this session's earlier synthetic-injection work) | (bit `0x40`) |

**Key correction to earlier-phase documentation**: `flags=0x80` was
previously named `PAGE_TRANSITION_CHECK` and described (in
`FRAME_RENDER_MODES.md`, written against the *chapter-0* profile) as "a
separate branch entirely, calls `FUN_8004ac5c`". **For this chapter-1
profile, that is not the case** — `flags=0x80` feeds directly into the
*same* mode-handler function as mode 0, as **mode value 2**, dispatched
by the identical `beq $s0,$v0,...` chain used for every other mode.
Whether chapter-0's profile genuinely has a separate branch, or whether
that was itself an approximation, is not re-tested here — this is
recorded as a confirmed difference for THIS profile specifically, not
a correction applied retroactively to chapter-0's own findings.

## Internal dispatch (fully disassembled, live-confirmed)

```
flags = *(sp+0x22)                 [master render loop's own frame]
mode  = *(sp+0x10)                 [handler's 5th argument, read at 0x8003a6c8]

if mode == 1:  goto 0x8003A7D0     [beq at 0x8003a708]
if mode <  2 and mode == 0: goto 0x8003A748   [fallthrough / mode-0 path]
if mode == 2:  goto 0x8003A81C     [beq at 0x8003a730]
if mode == 3:  goto 0x8003A78C     [beq at 0x8003a738]
```

An index counter at the fixed global `0x800A39DC` is read and
(for the non-mode-1 paths) stored to `0x800A3A08` early in every call,
regardless of which mode branch is ultimately taken.

## Per-mode findings

### Mode 0 (WIDTH_MODE — routine per-character reveal)

Falls through to `0x8003A748` and onward, converging by `0x8003a8a4`
into the **shared tail** described below. Fully traced in the previous
round of this investigation (see `EXPERIMENT_PLAN.md`'s prior section)
— calls candidate A (`0x8003AFFC`, glyph-cache write, RULED OUT) and
candidate B (`0x8003B224`, unrelated utility). No unique mode-0-only
code beyond the dispatch itself; it is effectively "run the shared
tail with no extra preamble."

### Mode 1 (RESET_MODE-shaped)

**Branch**: `0x8003A7D0`. **Unique behavior, not shared with any other
mode**: computes `struct_addr = s1(records_base) + index*14` (same
records array as mode 0, confirmed live: `s1` observed as
`0x800a2ad4`, identical to `a0`) and writes to that record's `+8`/`+0xA`
fields (the historical X/Y convention). Live-captured values:
`X=249, Y=191` and `X=258, Y=172` across two separate hits — both
plausible on-screen pixel coordinates, not the fixed off-screen-cache
shape (`X=320+`) seen for mode 0's candidates.

**Live-modification test**: performed twice (index 40 and index 23),
each time confirmed the record was genuinely fresh at write time
(`valid_flag=0`, not the `0xFFFF` "already consumed" sentinel — ruling
out a stale-timing explanation). Modified X to an extreme value (10)
in both cases, confirmed via readback, screenshotted while the
modification was still active. **Result: no visible movement of the
live dialogue text in either test.** RULED OUT as the primary
consumed-for-display X field, at least for the specific record indices
tested — see "Open question" below for the caveat this doesn't fully
close.

### Mode 2

**Branch**: `0x8003A81C`. Has its own preamble (`0x8003a828`-`0x8003a8a0`)
before falling into the same shared tail mode 0 uses. This preamble:

1. Checks a global (`0x800A39F2`) for a "negative" (top-bit-set) 16-bit
   value; if so, skips its own loop entirely and jumps straight to the
   shared tail.
2. Otherwise, runs a bounded loop (`beqz ...; ...; 1040ffeb` back-branch)
   walking the position-records array, checking each record's validity
   flag (`+0xC`, the same `0xFFFF` sentinel used throughout this
   project), and — for each valid record — **copies its Y field into a
   dedicated output array** at `0x800A3A0C` onward (2 bytes per entry).

This is structurally identical to this project's own documented
`Y_COLLECTION_MODE` behavior (mode 3), but reached **naturally and
frequently** during ordinary play (observed 4 times in one 200-second
sample), unlike mode 3 which required a synthetic script-word
injection to trigger at all.

**Live-captured real data — this session's first-ever non-empty Y
collection**: `Y=152` and `Y=171`, alternating consistently across 10
consecutive collection events. `152` is a direct, independent match
for the `Y=152` constant already established as a real on-screen line
position in the *original* chapter-0 investigation
(`TEXT_POSITION_TRACE_LOG.md`, event set A). This finally resolves the
earlier session's long-standing open item ("catch a genuinely
non-empty Y-value list").

**Live-modification test**: broke right after natural collection wrote
`152` to `0x800A3A0C`, modified it to `5`, confirmed via readback that
the modified value was **still present** at screenshot time (not yet
naturally overwritten). **Result: no visible movement of the live
dialogue text.** This is a real negative result (the value was
confirmed still active, not stale) — RULED OUT as a field the renderer
reads directly for the currently-displayed line. Most likely
interpretation: this is a *derived summary* (e.g. for a scroll/history
mechanism), not literally the value drawn from every frame.

### Mode 3

Not observed this round (matches the established rarity from earlier
in this session — needs a nonzero-parameter `pause_flag_a` script word,
naturally rare). Branch address confirmed via static disassembly
(`0x8003A78C`) but not live-captured in this round. Structurally
similar to mode 2's preamble (same records-walk-and-collect shape);
not independently re-verified this round given time budget — carried
forward from this session's earlier, separate mode-3 investigation
(`MODE3_TRIGGER_INVESTIGATION.md`).

## Shared tail (modes 0 and 2 converge here, `~0x8003a8a4` onward)

Already fully documented in `EXPERIMENT_PLAN.md`'s prior section:
calls candidate A (`0x8003AFFC`, RULED OUT — glyph-cache/texture-index
write) which itself nests a call to candidate C (`0x8003B144`, RULED
OUT — builds an off-screen-cache-shaped `(X,Y,W,H)` rect and uploads
it), then calls candidate B (`0x8003B224`, unrelated utility, `a0=0`).

## Master render loop's own post-handler processing (Phase 5 finding)

The master render loop does **not** stop at calling the mode-handler —
each call site is followed by additional processing:

- After the mode-1 call site (`0x80038c58`): writes `-1` to the index
  counter `0x800A39DC` (matches this project's long-standing
  "RESET_MODE resets the index" documentation).
- After the general call site (`0x80038ca0`): reads a byte flag at
  `0x800A39D9`; if it equals a specific value, calls **candidate D**
  (see below) and other nested functions (`0x80039390`, `0x80039554`)
  not exhaustively traced this round.

### Candidate D (`0x8003AAAC`) — new finding, most promising untested lead

Called from within `0x80039554` (itself called from the render loop's
post-handler section). Writes directly to the main records array's
`+8`/`+0xA` fields — **using the same records base (`a0`/`s0` =
`0x800A2AD4`) as everywhere else**, with source values combining a
per-line base struct (`s1 = 0x800A38D4`, offsets `+0`/`+2`) with the
records-base itself. Live-captured: `X=13, Y=152` (again, `Y=152` — the
third independent observation of this exact constant this round).

**Live-modification test**: modified X (13→10) at record index 0.
**Result: value had already reverted to its original (13) even before
the manual restore step** — meaning this specific write is recomputed
extremely frequently (likely every frame), faster than a
modify-then-screenshot round trip (which requires a separate process
invocation with real overhead) can outpace. This is NOT a "ruled out,
no effect" result — it is an inconclusive result due to a
methodology limitation, explicitly distinguished from a genuine
negative per this project's own "don't claim success/failure from an
untested case" discipline.

**This is the single most promising open lead**, and the precise next
task (see `VISIBLE_DIALOGUE_COMPOSITION_PATH.md` and
`EXPERIMENT_PLAN.md` for the concrete next step: modify the *source*
struct this computation reads from, not the destination, so the
next natural recomputation propagates the modified value instead of
overwriting it).

### Follow-up: candidate D's source traced, causal link still unconfirmed

A later round installed write watchpoints on `0x800A38D4`/`0x800A38D6`
and traced them to a generic struct-copy function (true entry
`0x800391CC`, one level of pointer indirection via `a0+0x14`) whose
source is a **static, compiled-in template at `0x80090AB0`** inside
CAP1.EXE's own data section — fields at `+0xC`/`+0xE` hold X=10, Y=152.
Modifying this static source **does propagate** through the chain, but
two live-modification rounds produced contradictory quantitative
results (round 1: delta 10→200 propagated to candidate D's destination
as 203, matching the documented "+3" offset; round 2: delta 10→60
propagated as exactly 60, with an unrelated intermediate value 38 in
between). The index counter (`0x800A39DC`) had advanced from a low
value to 26 between rounds, proving `record[0]+8` is a shared,
continuously-recomputed per-character slot that ordinary gameplay
overwrites during the multi-second observation windows these tests
require — contaminating the comparison. A tight chained-breakpoint
trial (avoiding any multi-second window) timed out because the copy
function doesn't fire while the game is idle at a choice-menu screen
awaiting player input.

**Verdict, updated by a later round: candidate D is now RULED OUT.** A
deterministic same-frame test (break at the copy entry → modify the
static source → break at candidate D → verify propagation → capture
the live record slot → single-step the store → continue to render →
screenshot immediately, before restoring) confirmed across two
independent deltas (10→230 and 10→160) that the modification survives
all the way to the record write (an EXACT copy, no offset — the
previously-reported "+3" was a sleep-based-methodology artifact, not
real) but produces **no visible movement** of the actual rendered
dialogue/choice-menu text. Full detail, including the profile-identity
verification that made this possible (a quickload landed back in this
exact chapter-1 profile) and cross-profile corroboration from the
"shifted" chapter-0 profile's own equivalent field, is in
`VISIBLE_DIALOGUE_COMPOSITION_PATH.md`'s "Deterministic same-frame
round" section. All static memory modifications were restored and
verified via readback.

## Layout drift log (Phase 8)

Recorded honestly, in chronological order, for whoever continues this:

1. At the start of this task's predecessor round, the profile was
   confirmed as chapter-0's "shifted" layout (hook-equivalent bytes at
   `0x8004a378` = `21808000`, matching this session's own established
   convention).
2. Within the same continuous session, without any quickload, the
   layout at that same address region changed to chapter-0's
   "original" layout (`addiu sp,sp,-0x20` at `0x8004a36c`, previously
   documented in `MIPS_PATCH_PLAN.md` as historically never firing).
3. Later in the same session, the decoder/cursor/render-loop addresses
   were found to match this session's own independently-mapped
   **chapter-1** overlay exactly (`0x800398A4` decoder entry) — the
   game had transitioned into a different loaded executable during
   ordinary "auto-transitioning" dialogue, not via any explicit reload
   the operator reported.
4. All addresses used in this document were captured and validated
   against that chapter-1 state specifically, and re-verified stable
   across the multi-minute capture rounds within this task (confirmed
   via repeated `validate_call_site`/direct byte reads at the start of
   each new phase).

**Practical implication, stated plainly**: no absolute address in this
document (or any other in this project) should be assumed valid at the
start of a future session without a fresh live check first. This isn't
a one-time caveat — it happened three times in one continuous
investigation.
