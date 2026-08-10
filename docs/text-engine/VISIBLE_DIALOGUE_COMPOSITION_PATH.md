# Visible Dialogue Composition Path

Candidate-by-candidate view of everything traced this round, cross-
referencing `MASTER_RENDER_MODE_MAP.md` (which organizes the same
material by mode instead of by function). All addresses are for the
chapter-1 overlay profile confirmed this session — see that document's
"Layout drift log" before reusing any of them.

## All candidates found, classified

| Candidate | Address | Called from | Classification | Evidence |
|---|---|---|---|---|
| A | `0x8003AFFC` | Mode 0/2 shared tail (`0x8003a900`) | **Glyph-cache upload** | Writes record `+0`/`+2`; live-modified → isolated corrupted-glyph artifact, real text unaffected |
| C | `0x8003B144` | Nested inside A (`0x8003b108`) | **Off-screen texture-cache prep** | Builds `(X,Y,W,H)` rect, `X=328/Y=320/W=4/H=16` — matches the already-ruled-out `FUN_8004aa08` cache-destination shape exactly; live-modified X → no visible change |
| B | `0x8003B224` | Mode 0/2 shared tail (`0x8003a90c`) | **Unrelated shared utility** | Called with `a0=0` (not a records-base pointer); reads unrelated struct fields; not position-related |
| Mode 1 write | `0x8003A7D0` | Master loop directly (mode==1) | **Unresolved (tested, no effect observed)** | Writes real-looking `(X,Y)` to the MAIN records array `+8`/`+0xA`; live-modified twice, confirmed fresh (not stale/consumed) at write time; no visible movement of live text in either test |
| Mode 2 collection | `0x8003a884` (loop inside mode-2 preamble) | Master loop directly (mode==2) | **Unresolved (tested, no effect observed)** | Naturally collects real Y-values (152, 171) into a dedicated summary array; live-modified, confirmed still-active at screenshot time; no visible movement of live text |
| D | `0x8003AAAC` | Master loop post-handler (`0x8003958c`, itself called from `0x80038ce4`-area processing) | **RULED OUT (confirmed via proper same-frame testing — see "Deterministic same-frame round" below)** | Copies MAIN records array `+8`/`+0xA` from source `0x800A38D4`/`+2` — confirmed via clean same-frame testing to be an EXACT copy, no offset (the earlier-documented "+3" was a sleep-based-methodology artifact, not real). Source traced to a static compiled-in template (`0x80090ABC`/`+0xE`) via a generic struct-copy function (`0x800391CC`). Modifying the source and single-stepping the full chain through to render produced NO visible movement of the actual dialogue/choice-menu text, across two independent deltas. |

## What this rules out, cumulatively (this round + prior rounds)

Six mechanisms have now been fully traced and live-tested across two
independently-compiled overlay profiles:

1. `FUN_8004a370`'s cursor fields (chapter-0 profile, prior session).
2. `FUN_8004a8c0`'s blit-position fields (chapter-0 profile, prior
   session).
3. The `FUN_8004aae8`/debug-print chain (chapter-0 profile, prior
   session).
4. Candidate A / `0x8003AFFC` (chapter-1 profile, this session).
5. Candidate C / `0x8003B144` (chapter-1 profile, this round).
6. Mode 1's `+8`/`+0xA` write and mode 2's collected-Y array (this
   round) — both tested with confirmed-fresh/confirmed-still-active
   values, genuinely negative results, not timing artifacts.

**Every one of these produces plausible-looking coordinate values and
either an isolated artifact or no visible effect at all when modified
— never a predictable movement of the actual live dialogue glyphs.**

## What remains: candidate D, precisely

Candidate D (`0x8003AAAC`) is the one lead this round did **not**
manage to rule in or out, for a specific, narrow, well-understood
reason: its write to the records array is recomputed far more
frequently than this project's current live-modification methodology
(read → modify via GDB `M` packet → separately invoke a screenshot
process → compare) can outpace. The modified value was independently
confirmed to have already reverted to its original by the time of the
*next* check, before any manual restore even happened.

This is fundamentally different from every RULED-OUT candidate above,
where a modified value was confirmed **still present** at screenshot
time and *still* produced no visible effect. Candidate D's case is an
inconclusive **methodology gap**, not a negative result — per this
project's own explicit "Invalid Success" list, this must not be
reported as ruled out.

### The exact next task

Two viable approaches, in order of expected reliability:

1. **Modify the source, not the destination.** Candidate D computes
   its `(X,Y)` from a per-line base struct at `s1 = 0x800A38D4`
   (offsets `+0`/`+2`), combined with the records base. If that source
   struct is written far less frequently than the per-character
   records-array entry it feeds, modifying it once should propagate
   through the *next* natural recomputation and stay visible for an
   entire line/textbox, giving a much wider and more reliable
   screenshot window than modifying the destination directly.
2. **Reduce the modify→observe latency.** Either keep the emulator
   paused at the breakpoint (don't send a final `c`) and take the
   screenshot while genuinely halted — checking first whether
   PCSX-Redux's display refreshes from the last-drawn framebuffer while
   the CPU is stopped, which would need to be established empirically,
   not assumed — or write a single combined script that does
   modify+screenshot-trigger in one process without a second tool
   invocation's overhead in between.

Approach 1 is recommended first: it requires no new tooling, only
locating and testing what actually writes `0x800A38D4+0`/`+2`, which is
a natural continuation of this same investigation (trace backward from
candidate D's own read, the same technique used to find every other
candidate this round).

## Follow-up round: tracing candidate D's source (`0x800A38D4`/`+2`)

Per Approach 1 above, installed GDB write watchpoints (`Z2`) directly on
`0x800A38D4` and `0x800A38D6` during active dialogue. 25 hits captured
over ~200s, all landing in an until-then-unmapped code region
(`0x80039268`–`0x800392a4`), called from exactly two sites
(`0x80038a20`, `0x800390f8`). Both call sites resolve to the same
function; its **true entry** (not the mid-function view first examined)
is `0x800391CC`, a generic multi-field struct-copy: it takes a pointer
in `a0`, dereferences `a0+0x14` to get a **source struct pointer**
(one level of indirection), and copies fields from that source into
`a2`/`a3`.

Live-captured the dereferenced source pointer: **`0x80090AB0`** — a
**static, compiled-in data address inside CAP1.EXE's own data section**
(16 bytes before the already-known `fonttbl` address `0x80090AE8` from
`cap1.ini`), not a runtime-computed value. The fields matching our
watched destination are at source offsets `+0xC` (`0x80090ABC`,
X=10) and `+0xE` (`0x80090ABE`, Y=152) — this Y value is the same 152
constant observed independently three separate times this session
(mode 2's natural collection, candidate D's own destination, and now
here), which is a meaningful cross-check even though it doesn't by
itself prove causality.

### Live modification: two contradictory rounds, methodology limitation identified

**Round 1** (sleep-and-poll, delta 10→200): modifying the static source
propagated to `0x800A38D4` within 3s and to candidate D's destination
(`0x800A2ADC`, records[0]+8) within 12s, landing at **203** (=200+3,
matching the previously-established "+3" offset) and holding for 18+
seconds. A screenshot taken at that point showed the active choice-menu
text visibly shifted far to the right of its normal position.

**Round 2** (same test, smaller delta 10→60, to check
reproducibility/proportionality): `0x800A38D4` again picked up the new
value (by +9s), but candidate D's destination passed through an
**unrelated intermediate value (38)** matching neither the old nor new
source value, then settled at **exactly 60 — not 63**. The "+3 offset"
from round 1 did **not** reproduce.

**Root cause found**: reading the index counter (`0x800A39DC`) after
round 2 showed it had advanced to **26**, and record slots 0–3 all held
mutually-different, plausible-looking `(X≈32-80, Y=152)` values with a
validity flag of `1` rather than the `0xFFFF` sentinel documented
earlier. This proves `record[0]+8` is a **shared, continuously-recomputed
per-character slot**: during the multi-second sleep-and-poll windows
needed to observe the low-frequency source copy, ordinary unrelated
gameplay (other characters/glyphs being rendered) kept overwriting the
same slot. Round 1's apparent "+3 offset, visible shift" result is
therefore **not proven causal** — it is at least as consistent with
coincidental timing (the screen had also naturally transitioned to the
choice menu around the same time) as with a genuine causal link.

**A tight chained-breakpoint test was attempted** (break at the
copy-function entry `0x800391CC` → modify source → arm a breakpoint at
candidate D → single-step its store → screenshot within ~0.3s, avoiding
any multi-second contamination window) but **timed out**: with the game
idled at the choice menu (not actively advancing text), the copy
function never fired within 60s. A liveness check confirmed the
emulator itself is not frozen (other state changes over a 2s window
were absent because the game is genuinely idle awaiting player input,
not because it's stuck) — this copy function appears gated on active
per-character text advancement, not free-running.

**Conclusion: candidate D and its source chain remain UNCONFIRMED, not
ruled out.** This is the correct call under this project's own
"Invalid Success" standard — a coincidental correlation under
contamination is not evidence of causation. The technical chain (source
producer, copy mechanism, propagation, offset behavior) is now fully
mapped and documented; what's missing is a clean, single-frame,
contamination-free trial, which requires either (a) a way to advance
dialogue under script control so the tight chained-breakpoint test can
run during active text flow instead of an idle choice menu, or (b) a
way to isolate one specific character's record slot from the shared
array so an 18-second observation window no longer risks contamination
from unrelated characters.

All static-source modifications made during this round were restored
immediately after each test (verified via readback: `0x80090ABC` =
`0a00` / 10, `0x80090ABE` = `9800` / 152, both matching original).

## Deterministic same-frame round: candidate D confirmed RULED OUT

A follow-up round replaced the sleep-and-poll methodology entirely with
a tight, chained-breakpoint sequence — the approach the earlier round
flagged as necessary but couldn't complete (it had timed out because
the game was idle at a choice menu with no active text advancement).

**Getting back to an active state**: the emulator was found halted
(`PC` pinned at `0x80000080` across a 1s gap) after the operator
paused it; resuming (`c`) and simulating a Cross-button press
(`keybd_event` targeting the PCSX-Redux window, matching
`pcsx.json`'s `Keyboard_PadCross=88`/`'X'`) restored real per-character
text processing, confirmed via the index counter changing across
polls.

**Profile identity check first**: a subsequent quickload landed in
what this project's own history called the "original" (non-shifted)
chapter-0 layout. Rather than assume, every chapter-1 landmark
(decoder entry, mode-handler entry, candidate D, the copy function,
the static source struct) was re-read live and matched byte-for-byte —
**this scene is the identical compiled chapter-1 profile**, not a
third distinct build. This matters: it meant candidate D's own chain
could be tested directly, with no re-derivation needed.

**The test**: break at the struct-copy entry (`0x800391CC`) → modify
the static source (`0x80090ABC`) before the copy body runs → remove
that breakpoint, arm one at candidate D (`0x8003AAAC`) → continue →
confirm `0x800A38D4` already reflects the modified value at that exact
instant → capture the index counter/record slot live (not assumed) →
single-step candidate D's store → verify the record → continue to
render (~0.2s) → screenshot immediately, before restoring.

| trial | delta | source→`0x800A38D4` | record write | screenshot result |
|---|---|---|---|---|
| 1 | 10→230 | 230 (exact match) | 230 (**exact copy, no "+3" offset**) | choice-menu text ("A：見るだけ見／B：うるさいな") rendered at its normal position — no shift |
| 2 | 10→160 | 160 (exact match) | 160 (**exact copy, no offset**) | dialogue text ("ユカリ：・・・／（とか言いつつ...）") rendered normally — no shift, no corruption |

**This corrects the earlier round's own finding**: the previously-
documented "+3 offset" (observed once, via sleep-and-poll, contaminated
by the index counter advancing 26 positions during the observation
window) does not reproduce under clean same-frame testing — both
trials here show an **exact** copy, no arithmetic transform. The
earlier "+3" was almost certainly a coincidental difference between
two unrelated characters' natural values, not a real computation
candidate D performs.

**Verdict: candidate D is RULED OUT** as the final on-screen dialogue
position writer — cleanly, this time, with the modification verified
present at every stage of the chain up through the actual render, and
reproduced across two independent deltas. Both static-source
modifications were restored and verified via readback immediately
after each screenshot.

## Cross-profile corroboration: the shifted-layout profile's own equivalent field, also ruled out

In the same round, before the quickload above, the SAME conceptual
field was independently tested in the "shifted" chapter-0 profile
(records base `0x800a3dd0`, wrap function `FUN_8004a370`, common exit
`0x8004a658` — see `MIPS_PATCH_PLAN.md` for the original, disassembly-
based ruling-out of this exact field). A fresh same-frame trial there
(break at `FUN_8004a370`'s entry to capture the live record slot,
break at its common exit to modify the FINAL settled X value, continue
to render, screenshot) reproduced the same negative result: modifying
`record[0]`'s X (10→220) produced no visible shift in the rendered
line ("ミカ：センパイ、夜の"), rendered at its completely normal
position.

One methodology lesson surfaced here worth recording: an initial
attempt modified at the FIRST observed write to the slot, not
realizing a single character (particularly one at a line-wrap
boundary) can write the same field multiple times within its own call
(five writes were observed for one wrapping character, settling from
195→181→181→195→10). Modifying at the first write got silently
overwritten by the character's own later internal branches before
render — this is what the parent task's "identify the exact
overwriter" requirement anticipates, and the overwriter here was the
SAME function's own wrap-reset logic, not an external consumer. The
fix was to break at the function's confirmed common exit instead,
guaranteeing the modification lands after all internal writes settle.

A second delta trial in this profile was attempted but its screenshot
capture failed due to a focus-grab timing issue (the scene had
transitioned to an unrelated real-time minigame by the time the
retry-loop finished) — recorded honestly as an infrastructure failure,
not a negative game-mechanism result. Given the strong three-way
convergence already available (this trial + the profile's own prior
disassembly proof + its own prior empirical test), this was not
pursued further.

## Round: tracing backward from the ordering table (DrawOTag) — the actual dialogue primitive found

With the entire `LoadImage`/`StoreImage`/`MoveImage` family exhaustively
ruled out (see the round above), this round reversed the search
direction entirely: start from the per-frame GPU ordering-table
submission (`DrawOTag`) and walk backward to whatever primitive is
actually queued for the visible dialogue text, rather than continuing
to guess at upload-primitive callers.

**Locating the real frame-submission functions**: the same PS1 SDK
debug-trace string table already used to find `LoadImage`/`StoreImage`/
`MoveImage` also contains `ClearOTag`, `ClearOTagR`, `DrawOTag`,
`PutDrawEnv`, `PutDispEnv` (contiguous strings starting at `0x8003750c`).
Locating each wrapper the same way (find the code that loads its own
name as a debug-print argument) and then reading the shared GPU
dispatch table (`0x8009c148` → `0x8009c108`, the same table `LoadImage`
dispatches through) gave the REAL, non-debug-wrapped implementation
addresses:

| function | wrapper | real implementation (table slot) |
|---|---|---|
| DrawOTag | `0x80074fc4` | `0x800767f4` → tail-calls `0x80076818` |

**Capturing a real frame's ordering table**: broke at `0x80076818`
during active dialogue, read `a1` (the OT head pointer, confirmed via
disassembly — the wrapper computes `RealDrawOTag(context, ot_ptr, 0)`),
then walked the tag-chain (`tag = size<<24 | next_addr`, terminator
`0xFFFFFF`) reading every linked primitive's raw words. A full walk
(not capped at 200 — the OT is much longer, 2124 total slots in one
capture, most empty priority buckets) and proper GPU packet decoding
(the real command byte is the top byte of the word AFTER the tag, not
adjacent to it — an early decoding mistake this round caught and fixed
before drawing conclusions) found, among other primitive families,
**24 `POLY_FT4` semi-transparent textured quads** (GP0 command `0x2E`)
with:

- X/Y vertex coordinates in the exact plausible on-screen textbox band
  (Y = 176–196, X ranging roughly -70 to +125) — matching every
  dialogue screenshot's textbox position throughout this entire
  session.
- U/V coordinates and three distinct CLUT/TPAGE value pairs cycling
  across quads, consistent with sampling a shared font-glyph texture
  atlas.
- Adjacent quads' X ranges connecting edge-to-edge (e.g. one quad's
  `[-10,53]` followed by the next's `[53,115]`), exactly the shape of
  sequential character placement along one line.

This is the actual visible-dialogue GPU primitive — found by reading
what the game itself already queued for drawing, not by guessing at
a candidate function.

### Tracing the exact writer

A write watchpoint on one quad's `xy0` field (packet offset `+8`) caught
the writer instruction directly: **`0x8007b250`**, disassembled as
`swc2 $12, 0($t0)` — a **COP2 (GTE) store**, not a plain ALU store.
Reading backward from there: the containing function (`0x8007b224`)
loads three vertex structs via `lwc2` into GTE data registers 0–5,
executes **RTPT** (`cop2 0x4a280030` — Rotate/Translate/Perspective
Transform, triple-point) at `0x8007b240`, then stores the resulting
`SXY0`/`SXY1`/`SXY2` screen-coordinate registers via `swc2` back into
the packet — confirmed by matching `0x8007b250` exactly against the
watchpoint hit.

**This means dialogue-glyph screen position is computed via the PS1
GTE hardware's perspective-transform unit**, not plain scalar
arithmetic — a genuinely different mechanism than every previously
investigated candidate (candidate D, both wrap-cursor fields, the
whole `LoadImage` family) all of which used ordinary ALU math. This
also explains why forward-searching from upload primitives never
found it: the actual compositor doesn't call any SDK image-upload
function at all, it builds a hardware-transformed textured-quad
primitive directly.

The function's caller (`0x80045014` return address, resolved via
`gcrts.mips_jal_decoder` against call site `0x8004500c`) builds the
three input vectors from a per-character struct (register `s4`,
fields at `+8`/`+0x10`/`+0x18`/`+0x20`) — the plausible next link back
toward the position-records array, not yet traced further given the
scope of this round.

### Live modification: propagation confirmed, visual confirmation not achieved

A same-frame test (break at DrawOTag's entry — at this point every
primitive for the frame is already built — modify one quad's X field,
then re-arm at the wrapper to catch the *next* frame's call before
halting, so the screenshot is taken from a genuinely stopped CPU
rather than racing a separate process against ongoing frame rebuilds)
was run twice successfully:

- Trial 1: X 103→283, confirmed present at the next frame's check.
  Screenshot showed the text ("ミカ：刺さなきゃいいい") rendered
  completely normally — **no visible shift**.
- A second attempt (X 192→372, Y=0 quad — later determined to likely
  be a UI blink/wait-icon element, not a line-of-dialogue glyph, given
  Y=0 doesn't match the 176–196 on-screen textbox band) also showed no
  shift, but is not a clean test of the *same* candidate as trial 1.

**Repeated attempts to get a second clean same-line confirmation were
not successful this round**, for a specific, well-understood reason:
dialogue text only gets freshly submitted to the ordering table during
the brief character-reveal moment (1–2 frames wide) — once a page is
fully typed and idle awaiting input, its already-drawn pixels simply
persist in the framebuffer without being re-queued, so most frames'
OT walks show no text-related primitives at all. Multiple approaches
were tried to catch this narrow window (aggressive per-frame key
presses, held-key fast-forward, single-press-then-check, breaking
directly on the GTE-transform builder function) without reliably
landing inside it — recorded honestly as a tooling/timing limitation,
not a negative finding about the mechanism itself.

**Verdict**: the dialogue-text GPU primitive and its exact position-
writing instruction are now identified with high confidence (a
concrete GP0 command, a concrete watchpoint-confirmed store
instruction, a concrete GTE operation) and one live trial showed no
effect from a modification confirmed present at the moment of render —
but this is **not yet a fully confirmed ruling-out**, since only one
clean same-candidate trial was completed rather than the required
two-delta repeat on the same textbox. The exact next task: catch a
second clean on-screen (Y 176–196) `POLY_FT4(semi)` trial — ideally by
first getting reliable programmatic control over dialogue advance
timing (e.g. a script-driven character-by-character step, or a
slower in-game text speed if the game's own options menu exposes one)
so the reveal window is no longer a 1–2 frame race.

All static memory modifications made during this round were confirmed
restored (verified via readback matching original values) before
concluding.

## Round: searching for the actual visible composition path (all LoadImage/StoreImage/MoveImage consumers exhausted)

With candidate D and both wrap-cursor fields ruled out, this round
searched outside the mode-handler/records-array chain entirely for
whatever actually builds the final on-screen primitive. Since the
previously-known GPU-upload address (`0x800786b8`) is stale in this
profile, the PS1 SDK's own debug-trace strings were used to relocate
the equivalent primitives directly: `LoadImage`, `StoreImage`,
`MoveImage`, `ClearOTag`, `DrawOTag`, `PutDrawEnv`, `PutDispEnv` all
appear as a contiguous string table at `0x800374e8`. Each function's
own wrapper was located by finding the code that loads its own name as
a debug-print argument:

| SDK function | wrapper entry |
|---|---|
| LoadImage | `0x80074ccc` |
| StoreImage | `0x80074d30` |
| MoveImage | `0x80074d94` |

Every caller of all three was found by scanning the complete 2MB PS1
RAM range (`0x80000000`-`0x80200000`) with `gcrts.mips_jal_decoder`,
not by hand:

- **StoreImage**: 2 callers (`0x800383d0`, `0x80071310`).
- **MoveImage**: 2 callers (`0x80038408`, `0x80038584`).
- **LoadImage**: 20 callers (full list captured in the round's own
  scratch output; see below for classification).

**Classification of every serious candidate found:**

| candidate | address | classification | evidence |
|---|---|---|---|
| candidate C's own chain | `0x8003b1e0`-`0x8003b23c` | **debug-trace logging** (already known) | calls into the tpage/clut bit-packing + printf-style dispatch confirmed via live string reads ("tpage: (%d,%d,%d,%d)...") |
| "swap" function | `0x80038370` | **unreachable / no confirmed caller** | StoreImage→MoveImage→LoadImage sequence that swaps two 16×1-pixel VRAM columns via a temp buffer; exhaustive search (direct JAL, raw data pointer, computed lui/addiu-then-jalr, and a live 30s breakpoint during active dialogue) found ZERO callers anywhere in RAM — flagged as the one genuinely unresolved item, not ruled out |
| single-MoveImage function | `0x80038548` | **sprite/portrait subsystem, unrelated to dialogue** | all 5 callers live in a distinct `0x8006xxxx` code region and pass an identical fixed constant (`a1=0x2c0`) — not a per-character variable |
| CG/picture-display function | `0x8003d904` | **CG/picture image display, not text** | computes tpage/clut via the same bit-packing helpers but for a scaling-mode image display (matches the framed photo/picture seen in one screenshot); only 1 caller, in the same isolated region |
| remaining 17 LoadImage callers | various (`0x8004xxxx`, `0x8007xxxx`, `0x8005xxxx`) | **fixed-asset loaders (title/logo/UI/background/CG streaming)** | every one builds a rect from CONSTANT dimensions (64, 128, 256px) or fixed static/streamed-buffer addresses — none reads a variable per-character width/height the way font-glyph rendering would require |
| post-handler bookkeeping (`0x8003b258`, `0x8003b408`, `0x8003b804`) | — | **record-lifecycle/timing state machines, unrelated to position** | invalidate stale record slots, dedupe-track small history buffers, and manage a frame-countdown — no coordinate or primitive construction |

**Conclusion: exhaustive, not final.** All 24 callers of the three
named PS1 SDK image primitives are now individually classified, and
none of them is the per-character dialogue compositor. This is a
genuine, hard negative result for this entire function family — the
real glyph-to-screen mechanism must NOT go through `LoadImage`/
`StoreImage`/`MoveImage` at all. No live acceptance test was run this
round because no candidate reached "serious screen-coordinate
candidate" status (per this round's own required classification step)
— every one was ruled out by structural/contextual evidence (fixed
constants, wrong subsystem, no discoverable caller) before qualifying
for a live modification test.

**The one open thread**: the "swap" function (`0x80038370`) remains
genuinely unresolved — it is structurally the most interesting
candidate (its args are variable, not fixed, and its behavior — swap
two VRAM columns via StoreImage/MoveImage/LoadImage — is exactly
shaped like a scroll or reflow primitive) but no caller could be found
by any static or live method tried. It may be reached via a
call-table/overlay-import mechanism this project's tooling doesn't yet
decode, or it may be genuinely dead code.

**Precise recommended next step**: rather than continue searching for
LoadImage-family callers, trace backward from the actual per-frame
ordering-table submission (`DrawOTag`, string-confirmed at
`0x8003750c`) or frame-flip point (`PutDrawEnv`/`PutDispEnv`) to see
what primitives are queued each frame — this reverses the search
direction (from "what's in the OT" instead of "what uploads pixels")
and would catch a raw sprite/quad-construction path that never calls
any of the three functions searched this round.

## Session-wide list of address families now mapped for chapter-1

For quick reference by whoever continues this (re-validate each with
`gcrts.mips_jal_decoder.validate_call_site` before trusting it):

- Decoder entry: `0x800398A4`
- Cursor global: `0x800A39EE`
- Script buffer (shared, fixed across all profiles): `0x801FE800`
- Render-loop dispatch (flags read): `0x80038B54`
- Mode-handler entry: `0x8003A6C0`
- Mode 1 branch: `0x8003A7D0`
- Mode 2 branch: `0x8003A81C` (preamble), collection write at `0x8003A884`
- Mode 3 branch (not live-retested this round): `0x8003A78C`
- Shared tail / candidate A: `0x8003AFFC`
- Candidate C (nested in A): `0x8003B144`
- Candidate B: `0x8003B224`
- Candidate D: `0x8003AAAC`
- Records array base: `0x800A2AD4`
- Per-line base struct (candidate D's source, next investigation
  target): `0x800A38D4`
- Index counter: `0x800A39DC`
- Mode 2's collected-Y output array: `0x800A3A0C` onward

## Round: tracing backward from the ordering table — full chain confirmed structurally, live confirmation inconclusive

This round followed the precise recommendation above: locate the real
`DrawOTag` implementation, break on it during active dialogue, walk
the submitted ordering table, classify every primitive, and trace the
strongest candidate's writer backward.

**Active DrawOTag chain** (all confirmed via `gcrts.mips_jal_decoder`,
not hand-calculated):
- SDK debug-trace string table at `0x800374e8` located the real
  wrapper functions (`ClearOTag`, `ClearOTagR`, `DrawOTag`,
  `PutDrawEnv`, `PutDispEnv`), independent of stale hardcoded chapter-0
  addresses.
- `DrawOTag` wrapper: `0x800767f4`. Real implementation (via the
  shared GPU dispatch table at `0x8009c148` → `0x8009c108`):
  `0x80076818`.
- OT pointer captured from `a1` at the implementation entry.

**OT walk + primitive decoder results**: a full, correctly-decoded
walk (GP0 command byte = top byte of the word *after* the tag word,
not adjacent-to-tag as first assumed) during active dialogue found
64×`POLY_GT4`, 55×`POLY_FT4`, **24×`POLY_FT4(semi)`** (GP0 `0x2E`),
14×`POLY_G3(semi)`, 3×`DRAW_MODE`.

**Dialogue-correlated primitives**: the 24 `POLY_FT4(semi)` quads sit
at Y=176–196 on screen with connecting X ranges matching sequential
characters, and CLUT/TPAGE pairs (`0x2018/0x0085`, `0x2058/0x0085`,
`0x2098/0x0086`) consistent with a font atlas. This is the dialogue
glyph primitive.

**Exact writer traced**: a write watchpoint on one such packet's xy0
field caught `swc2 $12,0($t0)` at `0x8007b250`, inside a function
starting at `0x8007b224`. Full disassembly of that function (Capstone
doesn't decode PS1 COP2 opcodes — decoded word-by-word with a manual
COP2 table) shows it:
1. Loads 3 vertex vectors via `lwc2` from `a0`/`a1`/`a2`.
2. `cop2 0x4a280030` = **RTPT** (rotate/translate/perspective
   transform, 3 points at once).
3. Stores `SXY0`/`SXY1`/`SXY2` to three destination pointers passed by
   the caller on the stack.
4. Loads a 4th vertex from `a3`, runs a single-point GTE transform
   (`RTPS`, raw word `0x4a180001`), and stores its result plus a
   flag/depth value to two more caller-supplied pointers.

Four vertices in, four screen positions out — this is a `POLY_FT4`
quad builder, not a generic utility.

**Call site**: exactly one place in the whole game calls this
function — `0x8004500c` (`JAL 0x8007b224`, return address
`0x80045014`). Because it is unique, breaking here needs no
return-address filtering.

**Caller-side structure (new this round)**: disassembling the caller
right after the call site shows the four destination pointers passed
in are `s4+8`, `s4+0x10`, `s4+0x18`, `s4+0x20` — i.e. they land inside
a single struct pointed to by `s4`, which also gets color/flag bytes
written at `s4+4..6` just before the call. This is shaped exactly like
a `POLY_FT4` packet. Immediately after, the caller calls
**`0x800774b4(ot_slot_ptr, s4)`** with `s4` unchanged. Disassembling
`0x800774b4` shows it is the classic PS1 SDK `addPrim` macro — it only
reads/writes the two structs' 4-byte tag words to splice `s4` into the
OT chain by **reference**; it does not copy any primitive data. This
means whatever is sitting in `s4`'s memory at the time `DrawOTag`
processes the OT *is* what gets rasterized — there is no missed copy
step between our write point and the GPU.

**Live modification protocol used**: arm both the call site and
`0x8007b250` as persistent breakpoints ONCE (not re-armed per
iteration — repeated `Z0`/`z0` cycling was reconfirmed this round to
desync the GDB stub, producing a pathological stale-hit loop), loop
purely on `continue`, and only accept a candidate whose *original*
X/Y already falls in the visible on-screen band (`0-320`, `160-210`) —
several earlier candidates showed clearly out-of-range X such as `-41`
(65495 as u16), which are almost certainly characters pre-laid-out
ahead of their reveal and not what's currently on screen.

**Live test results — three independent, validated trials, all
null**: every trial confirmed the modified X value read back correctly
and persisted through the `DrawOTag` call for that frame (proving the
write is real and not silently reverted), but produced **zero visible
change**, including a pixel-perfect (`diff.getbbox() is None`, max
byte diff `0`) whole-frame comparison against a freshly-captured
unmodified frame for the third trial. Zoomed crops at both the
original and target screen coordinates showed no missing glyph at the
source position and no new/faint glyph at the target position.

**Honest verdict**: the structural chain (OT → `POLY_FT4(semi)` →
`swc2` writer → RTPT/RTPS GTE builder → unique call site → `addPrim`
link-by-reference into the OT) is confirmed by static analysis with
high confidence and is very likely correct. The live pixel-level
confirmation remains **inconclusive** — not contradicted, but not
positively confirmed either — after three methodologically sound
attempts. Candidate explanations for the null result, none confirmed:
(a) PS1/PCSX-Redux double-buffering meaning the frame actually
displayed lags one further step behind the `DrawOTag` call than
tested (a "one frame further" retry was tried and also produced a
null result, weakening but not eliminating this theory); (b) this
exact scene's dialogue box may not have been genuinely advancing
during the verification window (the same line of text was observed
across every capture for an extended period this round, despite
button presses), which would make any single-frame edit
unfalsifiable regardless of correctness, since a static/idle redraw
gives no new visual information to change. This second point is the
more likely explanation and is the honest caveat on this whole round's
live-test conclusions.

**Environmental findings, unrelated to the code trace but consumed a
large fraction of this round**: PCSX-Redux's UI "Pause" and its
focus-loss "Idle" auto-pause are both separate from, and not reliably
overridden by, a bare GDB `continue` — recovering requires an explicit
`c` with a real settle delay (`~1.5s`), and after certain conditions
(possibly stuck debug state) a full process relaunch. This session's
launcher process (`pcsx-redux`, near-zero CPU) is distinct from the
actual emulator core process (`pcsx-redux.main`, where the GDB server
and the game window both actually live) — confirm the target PID
before debugging after any relaunch. The in-game dialogue-advance key
for this profile is **`D`**, not `X`/Cross as assumed for the entire
session up to this point. A script bug this round (a filter regression
that trusted any GDB stop as a real breakpoint hit) caused one real
but low-severity RAM corruption at addresses `0x1`-`0x4` from writing
through a garbage register value; it was diagnosed, fixed (pc/address
validation added back before any memory write), and resolved by
reloading the same pre-test savestate.

**Precise next step**: obtain a save state and a verified, actually-
progressing dialogue sequence (confirmed by watching the character
count/line visibly change over consecutive real seconds before
arming anything), then repeat the same live-modification protocol.
If the null result persists under a confirmed-live scene, escalate to
holding the modified value across several consecutive frames (patch
the value, then re-arm and re-write it after each of the next 2-3
`DrawOTag` calls) to rule out a buffering-lag explanation for good.

## Round: screenshot methodology bug found and fixed; live confirmation still not pinned down, but static proof strengthened

Follow-up round, same save-state family. Two significant findings.

**Screenshot capture bug (major, session-wide impact)**: the
screenshot helper used all session used `GetDC`+`BitBlt`, which is
well known to return stale/cached content for GPU-accelerated windows
(PCSX-Redux renders via hardware acceleration), especially after a
window resize. This was confirmed directly: `BitBlt` repeatedly
returned an old dialogue line that had long since been advanced past,
while `PrintWindow(hwnd, hdc, PW_RENDERFULLCONTENT)` on the exact same
live window immediately showed correct, current content. This means
a meaningful fraction of this session's earlier "frozen"/"no visible
change" observations must be treated as unreliable — the emulator
was very likely running and progressing normally in some of those
cases; the capture, not the game, was stale. `PrintWindow` is now the
standard capture method going forward. One caveat found this round:
`PrintWindow` (and `BitBlt`) both return solid black when the target
is genuinely halted via the GDB stub at the exact moment `DrawOTag`'s
wrapper is entered for the current frame — the GPU has not rendered
anything yet at that instant. Real content only appears once the
process is allowed to actually run enough to render and present a
frame.

**New live-test technique (sustained patching)**: because the
per-character screen position is recomputed fresh from source data
every frame (not read once and cached), a single-frame edit gets
silently overwritten by the very next frame's redraw before it can
ever be displayed. Fix: re-arm the store breakpoint without
disarming/rearming per iteration (per the earlier documented GDB-stub
desync risk), and on every hit for the *same* target address,
immediately rewrite the modified value again — sustaining the edit
across N consecutive frames — before finally letting the CPU run
enough to actually render and present.

**Result**: every attempt this round to actually observe the sustained
edit ran into the same practical obstacle — this particular save
state sits inside a fast, apparently auto-advancing narrated
walking/cutscene sequence (character names/lines change every
1-2 seconds on their own, independent of button presses), which
consistently outran the multi-step patch→release→screenshot pipeline;
by the time a screenshot was taken, the scene had already moved past
the specific dialogue line/character that was patched, or past
dialogue entirely into a text-free establishing shot. No confirmed
false result was produced this round (unlike the earlier "zero pixel
diff" conclusion, which is now suspect given the capture bug) — the
live pixel-level confirmation remains simply **not yet obtained**,
for tooling-pacing reasons, not a contradicting result.

**Independent static confirmation (new, strong)**: disassembled the
caller of the GTE quad-builder (right after `0x8004500c`) and the
function it calls immediately after building the quad,
**`0x800774b4`**. That function is the classic PS1 SDK `addPrim`
macro: it only reads and rewrites the two structures' 4-byte OT tag
words to splice the primitive into the ordering-table chain **by
reference**; it does not copy any vertex/color data. Combined with the
caller writing color bytes at `s4+4..6` and the GTE builder's four
`swc2` stores landing at `s4+8`, `+0x10`, `+0x18`, `+0x20` (matching a
`POLY_FT4` packet layout exactly), this is strong, timing-independent
evidence that whatever is in `s4`'s memory at `DrawOTag` time is
exactly what gets rasterized, with no intermediate copy step this
chain could be missing. This static proof does not depend on
screenshot timing at all and is arguably more conclusive than a single
live pixel test would be.

**Environmental findings this round**: the in-game dialogue-advance
key is confirmed to be **`D`** (not `X`/Cross, corrected earlier this
document too casually assumed). PCSX-Redux's "Idle" status is shown
both for its own focus-loss auto-pause and for a genuine GDB-halted
target — the two are not the same underlying condition but produce
the same label. A relaunch of the emulator process is necessary after
certain stuck states; the actual emulator core lives in a child
process (`pcsx-redux.main`) distinct from the launcher (`pcsx-redux`)
that spawns it — always confirm the GDB port and the visible window
belong to the same PID after any relaunch.

**Verdict, honest**: structural chain confirmed to a high degree of
confidence, now including a timing-independent static proof
(`addPrim` links by reference, not copy). A clean, unambiguous live
pixel-level demonstration has not yet been captured, purely for
pacing/tooling reasons against this save state's fast auto-advancing
scene — not because of any contradicting evidence. Recommended next
step: repeat the same sustained-patch protocol against a save state
sitting in a slow, manually-paced conversation (a scene that visibly
waits for a button press for several real seconds, not an auto-playing
narrated sequence), which should give the multi-step pipeline enough
of a stable window to land a screenshot on the same dialogue line that
was patched.

## Round: emulator-state controller built; two distinct dialogue renderers discovered

Full detail for this round lives in three new documents to keep this
file from growing unmanageably long:

- **`RENDERER_LIVE_PROOF.md`** — the authoritative record of this
  round's work: the full structural chain restated, every live attempt
  with its exact outcome, the two bugs found and fixed (a vertex-read
  bug that rejected 500 real hits, and a wrong-breakpoint-pairing
  regression), and the precise final verdict.
- **`PCSX_REDUX_CAPTURE_PROTOCOL.md`** — the distilled operating
  procedure for driving this project's PCSX-Redux/GDB setup safely
  (process identity, resume semantics, breakpoint arm/disarm
  discipline, screenshot method, overlay-drift handling, control
  mapping, multi-renderer awareness).
- **`BREAKPOINT_GENERATION_LOG.md`** — the generation-tracked
  breakpoint session log format and this round's concrete sessions.

**One-paragraph summary**: the previously-identified renderer chain
(`0x8004500C` → `0x8007B224` → `0x8007B250` → `0x800774B4` addPrim →
OT → DrawOTag) was reconfirmed reliable — including a new static proof
that `addPrim` links primitives by reference, not by copy — but this
game turns out to have **at least two structurally distinct dialogue
renderers**. The identified chain only covers plain conversation
boxes; a separate, not-yet-identified mechanism renders the
portrait/photo-inset dialogue and the full-screen A/B/C choice menu
(proven separate, not just "different caller," since the shared writer
instruction never fires during that UI's active text reveal even when
armed without any caller filter). The live pixel-movement proof was
not completed this round because the available playthrough segment
was dominated by the second, unidentified renderer's content. No
memory write was ever made this round — every candidate was safely
rejected by pre-write validation before a write could happen.

**Update from a later session** (see `RENDERER_LIVE_PROOF.md` section
10 for full detail): re-tested `0x8004500C` directly against both an
ordinary dialogue line and a full-screen A/B/C choice menu in that
later session — neither triggered it even once over several minutes of
real playtime. The shared plain-writer instruction (the one this
document says covers "plain conversation boxes only") was instead
confirmed firing for *both* the photo-inset dialogue and the
choice-menu text in that session. This conflicts with this section's
"proven separate" conclusion above; the discrepancy was not resolved
between the two sessions (possibly different specific scenes/moments
were tested under the same general label), and is flagged here rather
than silently overwritten. What that later session did conclusively
resolve is *why* the live pixel-movement proof kept failing regardless
of which renderer was involved: the primitive array is a write-only
destination, refreshed every cycle from a separate source register
(`$s1`); editing the source instead of the destination produced the
first successful, reversible, visually-confirmed live edit.
