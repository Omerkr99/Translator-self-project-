# Text Position Source — Investigation Plan

Goal (per the task that opened this investigation): identify the exact
runtime producer of the X/Y coordinates that position live dialogue
glyphs on screen. Not "a plausible field" — the actual data-flow chain,
confirmed by live modification, not static analysis alone.

## Latest round: full mode dispatch mapped, one inconclusive lead remains

See `MASTER_RENDER_MODE_MAP.md` and `VISIBLE_DIALOGUE_COMPOSITION_PATH.md`
for full detail. Summary: the chapter-1 overlay profile's entire
per-character render-mode dispatch (modes 0/1/2/3) is now mapped, with
every reachable candidate this round live-tested. Seven mechanisms
across two overlay profiles are confirmed ruled out (artifact-only or
no visible effect, always confirmed via a modified value still active
at screenshot time — never a stale-timing false negative). One
candidate (`0x8003AAAC`, in the master render loop's own post-handler
processing) writes real coordinate-shaped values to the same records
array but recomputes faster than the current test methodology can
observe — explicitly inconclusive, not ruled out. Next step: trace its
source struct (`0x800A38D4`) backward and test that instead.

## Status (prior rounds): Partial success — real source narrowed, not yet fully identified

Two full hypotheses have been disassembled, live-sampled, and
empirically tested this session. Both are now ruled out as the FINAL
on-screen position mechanism (see `TEXT_POSITION_TRACE_LOG.md` for the
row-by-row evidence). A third mechanism has been found and partially
traced, but not yet confirmed as the answer — this is the current
frontier.

## The pipeline mapped so far

One call site (`FUN_80048e18`, called once per script character) calls,
in order:

1. **`FUN_8004a370`** ("the wrap function") — computes a real,
   proportional cursor position and writes it to position-record
   offsets `+8` (X) / `+0xA` (Y). Confirmed live: X advances by real
   glyph widths (16, 12, 14, 12...), Y stays constant within a line.
   **Modifying this field produces NO visible change** in rendered
   text — confirmed by live modification test. Ruled out as the
   mechanism that actually places pixels on screen (it may still be
   the correct LOGICAL position that something else later reads, but
   nothing found so far reads it for drawing).

2. **`FUN_8004a8c0`** → **`FUN_8004aa08`** ("the cache-populate
   function") — decompresses the current character's glyph bitmap
   (via `FUN_8007681c`, the already-known decompression routine) and
   calls a GPU-upload primitive (`0x800786b8`) to place it into VRAM at
   a destination that turned out to be **X=320, Y=256, W=4, H=16,
   advancing by a fixed +4 every character** — a fixed-stride,
   16-cells-per-row grid, unrelated to proportional glyph width, and
   at X/Y coordinates outside a standard 320x240 visible framebuffer.
   Writes its own working fields to position-record offsets `+0`/`+2`.
   **Modifying `+0` DOES produce a visible artifact** (a stray,
   disconnected dot) — proving it feeds something on screen — **but the
   actual dialogue text stays completely normal regardless**, ruling
   this out as the primary text-position mechanism too. Current
   best-supported interpretation: this populates an off-screen VRAM
   texture cache (a glyph atlas / font cache), not the visible
   framebuffer directly.

3. **`FUN_8004aae8`** → **`FUN_8007ad74`** — the next call in the same
   per-character sequence. Disassembly shows real PS1 GPU primitive
   construction: bit-packing consistent with texture-page/CLUT
   attribute encoding, and an indirect call (`jalr $v1`) through a
   function-pointer table at a fixed address (`0x8009d448`) — the
   standard PSn00bSDK pattern for submitting a GPU packet. **Not yet
   fully disassembled or live-tested.** This is the leading candidate
   for where the wrap function's cursor (the real logical position)
   and the texture cache populated by step 2 finally come together
   into an actual on-screen sprite/polygon draw command.

## What's confirmed ruled out (do not retest without new evidence)

- `FUN_8004a370`'s cursor fields (record `+8`/`+0xA`) as the direct
  screen-draw position.
- `FUN_8004a8c0`'s blit-prep fields (record `+0`/`+2`) as the direct
  screen-draw position — confirmed a real but secondary/cache effect.

## Major structural finding (follow-up round): the per-frame/per-character link found

A whole-code-segment byte-pattern search for the record-index multiply
(`sll;subu;sll`, the same 12-byte pattern confirmed throughout this
investigation) turned up a genuinely new function, `FUN_80049f84`
(`0x80049f84`), that:

- Is called from **`FUN_800481b0`, the master render loop, exactly
  twice** (`0x8004851c`, `0x80048564`) — confirmed via a JAL scan, this
  is the first function found this session that runs at the PER-FRAME
  level rather than per-character.
- Calls `FUN_8004a250` (the reference-index management helper found
  earlier), then branches on a 5th (stack) parameter into one of
  several modes (0, 1, 3 confirmed to exist from the two call sites'
  own dispatch logic).
- **Mode 3 contains a loop that walks the position-records array
  sequentially** (`v1 += 0xe` per iteration, matching the established
  14-byte stride), checking each record's validity flag (offset
  `+0xC`, the `0xFFFF` sentinel already documented) and, for each valid
  record, **copies its Y field (offset `+0xA`) into an output buffer**,
  capped at 4 entries — matching the already-documented
  `MAX_VISIBLE_LINES = 4` constant from `gcrts.layout_validation`.
  **This is a genuine, confirmed consumer of the wrap function's Y
  cursor field** — directly overturning this document's earlier
  statement that no such consumer had been found.
- Is called with `a3 = sp+0x18` (`FUN_800481b0`'s own local stack
  buffer) as the output destination, and immediately afterward,
  **`FUN_800481b0` calls `FUN_80048e18` — the SAME per-character
  caller studied all session (the one invoking `FUN_8004a370`,
  `FUN_8004a8c0`, `FUN_8004aae8`) — passing that SAME buffer as ITS
  `a3`.** Live-confirmed: breaking at `FUN_80048e18`'s entry from this
  call path shows `a3 = 0x801ffe10`, a genuine stack address in
  `FUN_800481b0`'s frame, not a static data address — proving this is
  the per-frame call, not one of the (also real) per-character calls
  to the same function.

**Refined via a 4-hit follow-up capture**: every hit at
`FUN_80048e18`'s entry showed the IDENTICAL stack address
(`a3 = 0x801ffe10`) across all 4 — meaning `FUN_80048e18` is called
**once per frame** from this master-render-loop call site, not once per
raw character as this session had assumed throughout. The value at
buffer offset `+8` (what `FUN_8004a370`/`FUN_8004a8c0` read as their own
`a3` via `lh a3,8($s2)`) varied frame to frame: 78, 52, 251, 115. Three
of the four are consistent with a `char_width<<3`-shaped value (roughly
7-14px widths × 8), matching this project's own earlier-established
understanding of that field from `gcrts.text_fitting`'s docstring — NOT
a Y-coordinate (which stayed constant within a line at ~150-250 in
every direct wrap-cursor capture this session).

**Conclusion**: the SAME local buffer (`sp+0x18` in `FUN_800481b0`'s
frame) serves at least two different roles depending on which mode
`FUN_80049f84` was called with earlier in the same frame — "current
character's width" in the common, every-frame reveal path (which these
4 captures landed on), and "collected valid-line Y positions" in mode
3's less-common branch (confirmed to exist by disassembly, not yet
caught live — mode 3 is likely tied to a rarer event such as a scroll/
line-transition, not the steady per-character reveal cadence this
capture round observed). Both are real, confirmed mechanisms; they are
just not the same thing at the same time. This is a genuine
nuance, not a contradiction — the earlier "genuine consumer of the Y
cursor" finding stands for mode 3, while the routine reveal path
consumes width data from the same memory instead.

## Mode table now confirmed with live data — see `FRAME_RENDER_MODES.md`

The mode flag driving `FUN_80049f84`'s branch is not arbitrary internal
state — it's literally the return-flags output of `FUN_80049168`, this
project's already-known script-bytecode decoder, written to a stack
buffer `FUN_800481b0` owns. Two rounds of live capture (40 hits total,
one specifically timed around a confirmed 4-full-visible-line textbox)
built a real mode table: `WIDTH_MODE` (flags `0x02`) and `RESET_MODE`
(flags `0x12`, unexpectedly the MOST common outcome at 65% of hits) are
both confirmed live. **`Y_COLLECTION_MODE` (mode 3, flags with bit
`0x40` set) — the mode containing the Y-position-collecting loop — was
NOT caught live in either round**, despite deliberately targeting the
4-line boundary. This is an open gap, not a ruled-out hypothesis; full
detail and the mode-by-mode evidence table are in
`FRAME_RENDER_MODES.md`.

## Precise next experiment

Fully disassemble `FUN_8004aae8` (both branches — the `beqz` at
`0x8004ab30` splits into two GPU-packet-building variants with
different shift constants, `srl a1,v0,9`/`srl a2,v0,7` vs.
`srl a1,v0,7`/`srl a2,v0,5`) and `FUN_8007ad74` (both call sites)
completely, to find where screen-destination X/Y (as opposed to
texture-source X/Y) enters the GPU packet. Then live-test by breaking
at that point and modifying the destination fields specifically —
following the same "verify empirically, not just numerically" rule
this document's own evidence was held to.

## Tooling built this session (durable, reusable)

- `gdb_proper_client.py` (scratchpad) — fixed two real protocol bugs:
  missing `+` acknowledgment (ack-mode is on by default per
  `qSupported`), and the target needing an explicit `c` after a fresh
  connection's `Z0` (it starts halted, contrary to the original
  assumption that the first hit "arrives on its own").
- `glyph_event_capture.py` — bounded (max 10 hits), JSON-exporting
  capture of destination rect + record state at the GPU-upload call
  site, one row per glyph event.
- `multi_shot_breakpoint.py`, `position_override_test.py` /
  `position_override_test2.py` — bounded multi-hit sampling and
  single-hit live modification test scripts.

## Constraints honored

No Phase 10 work. No custom renderer written. No live memory location
guessed without a marker-verified safety check. Existing decoder/
encoder/editor/injection pipeline untouched. All 269 pre-existing tests
still pass. Repository returned to a clean state (no breakpoints or
hooks left installed) after every experiment.
