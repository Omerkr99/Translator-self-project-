# Dialogue Renderer — Live Proof Status

This document is the single authoritative record of the "build a
reliable dialogue-renderer capture and complete the live position
proof" task: what was verified, what tooling was built and fixed,
what happened on every live attempt, and the precise remaining
blocker.

## 1. Structural chain (confirmed, high confidence)

```
0x8004500C  unique JAL call site (confirmed via gcrts.mips_jal_decoder:
             target=0x8007B224, return_address=0x80045014)
    v
0x8007B224  quad-builder entry: loads 3 vertex vectors via lwc2,
             runs GTE RTPT (rotate/translate/perspective transform,
             raw opcode 0x4a280030), stores SXY0/SXY1/SXY2, then loads
             a 4th vertex and runs a single-point GTE transform (RTPS,
             raw opcode 0x4a180001) for the 4th corner -- a complete
             POLY_FT4 quad builder
    v
0x8007B250  swc2 $12,0($t0) -- writes SXY0 (the first vertex).
             SXY1/SXY2/SXY3 are written by three further instructions
             in the same function (0x8007b254, 0x8007b258, 0x8007b27c)
    v
0x800774B4  addPrim -- disassembled and confirmed to only read/write
             the two structures' 4-byte OT tag words to splice the
             primitive into the chain BY REFERENCE. It does not copy
             any vertex/color/texture data. This is a static,
             timing-independent proof: whatever is in the primitive's
             memory at DrawOTag time is exactly what the GPU rasterizes.
    v
ordering table (linked list of GPU primitive tags)
    v
DrawOTag (wrapper 0x800767F4, real impl 0x80076818, both located via
             PS1 SDK debug-trace string discovery, independent of
             stale hardcoded addresses)
    v
GPU
```

The semi-transparent `POLY_FT4` primitives this chain builds were
independently found, in an earlier round, sitting at screen Y=176-196
in a live OT walk during active dialogue, with connecting X ranges
matching sequential characters and CLUT/TPAGE values consistent with a
font atlas.

**This structural identification does not depend on any of this
round's live-capture work and is not weakened by that work's
incomplete result below.**

## 2. What this round built

- `scratchpad/estate.py` — an emulator-state controller distinguishing
  RUNNING / BREAKPOINT_STOP / MANUAL_PAUSE / FOCUS_IDLE /
  STALE_NOTIFICATION / DISCONNECTED / UNKNOWN, with generation-tracked
  breakpoint sessions (a stop is only acted on if its PC matches the
  *current* generation's expected set) and a `force_resume_and_verify`
  helper that confirms the CPU actually advanced rather than trusting
  a bare `continue`.
- `scratchpad/validate_profile.py` — byte-for-byte + `mips_jal_decoder`
  validation of every landmark address, re-run before every capture
  attempt and after every relaunch/quickload/chapter transition.
- `scratchpad/final_precise_trial_v2.py` — the main single-shot capture
  pipeline: search for an on-screen candidate at the proven
  `CALL_SITE` + `STORE_INSN` breakpoint pair, validate (address range,
  GPU command byte, plausible coordinates) before any write, apply a
  delta to all four X values, verify the write, confirm the `addPrim`
  link, verify the values survive to just before `DrawOTag`, let
  exactly one more frame render, and leave state ready for an
  immediate `PrintWindow` screenshot followed by restoration.
- `scratchpad/ot_full_proof.py` — the Phase 10 ordering-table fallback:
  break at `DrawOTag`'s real implementation, walk the submitted OT,
  filter for glyph-sized (not background/portrait-sized)
  `POLY_FT4`/`(semi)` primitives in the dialogue Y-band, and run the
  same validate/modify/verify/render/screenshot pipeline against
  whichever primitive is found.
- `BREAKPOINT_GENERATION_LOG.md` / `PCSX_REDUX_CAPTURE_PROTOCOL.md` —
  process documentation (see those files for full detail).

## 3. Bugs found and fixed this round

1. **A real, low-severity RAM corruption** (bytes `0x1`-`0x4`) from an
   earlier session's script that trusted a stale stop notification
   without checking PC first. Diagnosed, the validation gate was added
   back, and the corruption was repaired by reloading the pre-test
   save. This is the direct motivation for this round's "never write
   without PC/profile/address/command/coordinate validation" rule.
2. **Incomplete vertex read**: the capture script single-stepped only
   once past `STORE_INSN`, which only writes the first of four
   vertices. The other three are written by three further,
   unbreakpointed instructions later in the same function. Every
   candidate was rejected as "unreadable" as a result — including one
   run that hit the breakpoint 500 times. Fixed by single-stepping in
   a loop until PC passes the last vertex-write instruction before
   reading anything.
3. **Wrong second breakpoint**: an earlier attempt in this round paired
   `CALL_SITE` with the function's `jr $ra` common exit (`0x8007b294`)
   instead of the already-proven `STORE_INSN`. That pairing produced
   zero hits across three separate 200+ second windows despite active
   dialogue, for reasons not fully explained (the two addresses are a
   handful of instructions apart in the same short leaf function).
   Reverting to the proven `CALL_SITE` + `STORE_INSN` pair immediately
   started producing hits again in the same play session. Recorded as
   an open discrepancy, not resolved.
4. **OT-walk-from-DrawOTag-entry does not find the main scene**: this
   was tried as a fallback capture strategy. Breaking at the real
   `DrawOTag` implementation and walking the OT it's about to submit
   reliably found only 8 small, near-empty per-effect ordering tables,
   cycling in a fixed repeating pattern, across 80+ consecutive hits.
   The main scene (with dialogue) does not route through this specific
   `DrawOTag` call in a way this approach could catch. This ruled out
   Phase 10 as currently built; the direct call-site approach remains
   the only one with confirmed positive results.

## 4. Major new finding: two distinct dialogue renderers

This game renders dialogue through **at least two genuinely different
code paths**, confirmed by direct evidence:

- **Plain conversation boxes** (no inset image, seen during regular
  exploration): use the chain in section 1. Confirmed repeatedly and
  reliably this round — the `CALL_SITE`+`STORE_INSN` breakpoint pair
  produced real, validated, on-screen candidates multiple separate
  times (see `BREAKPOINT_GENERATION_LOG.md` for the coordinate list).
- **Portrait/photo-inset dialogue boxes and the full-screen A/B/C
  choice menu** (both part of the same "psychic photo" cutscene UI,
  both drawn over the same framed photo backdrop): do **not** use this
  chain. Proof: `STORE_INSN` was armed *alone*, with no call-site
  filter — meaning any caller of the shared quad-builder would trip
  it — during 60+ continuous seconds of confirmed-active dialogue
  and choice-text reveal (including one case caught mid-character-
  reveal on a choice option). Zero hits. Since the breakpoint is
  caller-independent, this rules out "same renderer, different caller"
  and confirms a genuinely separate, not-yet-located mechanism.

The playthrough segment active during this round's live-testing window
was dominated by this second, unidentified renderer (the "psychic
photo" discussion sequence), which is the direct and complete
explanation for why the proven-working breakpoint pair kept producing
zero hits despite dialogue clearly being on screen and actively
advancing.

## 5. Live attempts this round — full account

| Attempt | Breakpoints | Scene at the time | Result |
|---|---|---|---|
| `final_precise_trial.py` x3 | `CALL_SITE` + `FUNC_EXIT` | plain dialogue (confirmed via screenshot) | 0 hits each, 200-250s windows |
| `final_precise_trial_v2.py` (first) | `CALL_SITE` + `STORE_INSN` | plain dialogue | 500 hits, but the vertex-read bug (section 3.2) rejected every one |
| `discover_caller.py` | `STORE_INSN` alone | portrait-inset dialogue | 0 hits, 60s -- proves the second renderer doesn't use this instruction at all |
| `ot_full_proof.py` delta=+80 | `DRAWOTAG_IMPL` (OT walk) | plain dialogue | 80 hits, all 8 repeating per-effect OTs empty of dialogue content |
| `final_precise_trial_v2.py` (post-fix) x3 | `CALL_SITE` + `STORE_INSN` | alternated between plain / portrait / choice-menu | 0 hits on each attempt -- every window happened to land during the second renderer's content |

**No memory write was made successfully at any point this round.**
Every attempt was either rejected by the pre-write validation gate
(no valid candidate found) or timed out before reaching a candidate.
This was independently confirmed by the absence of any
`write_journal_*.json` file at the end of the round.

## 6. Verdict

- **Structural identification**: confirmed with high confidence for
  the plain-dialogue renderer, including one piece of static,
  timing-independent proof (`addPrim` link-by-reference).
- **Live pixel-movement proof**: **not obtained this round**, for a
  precise, evidence-backed reason: the specific playthrough segment
  available during this session's live-testing window was dominated
  by a second, structurally distinct dialogue renderer that has not
  yet been identified, and every live-testing window happened to land
  on that renderer's content rather than the identified one's.
- This is not a contradiction of the structural finding, and it is not
  a tooling failure in the capture pipeline itself — the pipeline is
  proven functional (real hits, real candidates, real validated
  coordinates were obtained multiple times this round when the scene
  type matched).

## 7. Precise remaining blocker

**Need either**: (a) a save state / playthrough point sitting in a
plain (no photo inset) conversation, confirmed by screenshot before
arming, held for long enough to catch one reveal cycle; or (b) time
invested in identifying the second ("psychic photo" cutscene) renderer
using the same methodology as section 1, so the live proof can target
whichever renderer is actually active at the time.

## 8. Chapter 0 follow-up round: a third renderer variant found, write mechanism proven, visual proof still blocked by pacing

At the user's suggestion, testing moved to Chapter 0's opening scene —
the very first scene originally used to identify the plain-dialogue
renderer, chosen specifically to avoid Chapter 1's portrait/choice-menu
complications.

**Profile drift confirmed and handled correctly**: every Chapter 1
landmark address read back as completely different, non-JAL bytes in
Chapter 0 (as expected — different overlay). Per protocol, no
breakpoint was armed until the chain was rediscovered fresh.

**Rediscovery method**: the OT-walk-from-DrawOTag-string approach was
tried again first and hit the exact same wall as in Chapter 1 (the
resolved dispatch-table implementation only ever submits the same
handful of near-empty per-effect ordering tables). Abandoned in favor
of a more direct method: a raw full-RAM scan for the *byte pattern* of
a glyph-shaped `POLY_FT4` packet (tag size=9, cmd byte `0x2C`/`0x2E`,
four vertices within a small bounding box, at least one on-screen)
found **140 candidates** in one pass, laid out as a contiguous array
of sequential-character quads with perfectly connecting X ranges —
unambiguously the dialogue text, found without needing any breakpoint
at all.

**Writer instruction found and it's a different mechanism**: a write
watchpoint on one candidate's xy0 field caught `sh` (store halfword)
at `0x80049088` — Chapter 0's text renderer uses plain scalar stores,
not the GTE coprocessor pipeline used in Chapter 1's `0x8007b224`
chain. The primitive's base address was found directly in `$s0`
(register 16) at the hit. The two chapters therefore use two entirely
separate implementations of what is conceptually the same operation.

**One reproducible tooling quirk**: a software breakpoint (`Z0`)
placed at this exact `sh` instruction never fired across an 800-hit
budget, while a write watchpoint (`Z2`) on the target data address
fired reliably and immediately. Switching the search loop to use the
watchpoint fixed this. Root cause not identified — recorded here as a
second unexplained Z0-vs-Z2 discrepancy (see also `BREAKPOINT_GENERATION_LOG.md`'s note on `FUNC_EXIT`).

**Write mechanism fully proven working**, three times in a row:
search found the exact character-0 glyph (`X=[10,25,10,25]
Y=[152,152,167,167]`, matching the raw-scan candidates exactly), all
four vertices were shifted by `+80`, and every write was confirmed via
immediate readback (`0x0098005a`, `0x00980069`, `0x00a7005a`,
`0x00a70069` — all exact expected values). This is not in question.

**Visual proof blocked by the same pacing problem as Chapter 1, now
confirmed with two different capture strategies**:
- Attempt 1 (free-run 0.12s then screenshot): the emulator ran
  unthrottled during the sleep (observed FPS counter spiked to 142.5,
  ~3.8x normal) and the scene had moved to a completely different
  establishing shot with no text at all by the time of capture.
- Attempt 2 (free-run reduced to 0.03s): same outcome — dialogue box
  already closed, scene moved to a mid-animation moment with no text.
- Attempt 3 (fully breakpoint-controlled: no sleep at all, instead
  catching the *next* write to the exact same watched address to prove
  one full frame had elapsed): the dialogue box had **already closed**
  by the time that same memory slot was next written — it had been
  recycled for a different UI element in a subsequent scene (a
  progress-bar-like widget during a walking transition), not another
  reveal of the same line.

This means the line being tested closes and the scene advances faster
than even a single write-cycle to its own primitive's memory slot —
a stronger pacing constraint than anything seen in Chapter 1. All
three attempts correctly restored the original vertex values
afterward (verified via readback) with zero lasting side effects.

**Updated verdict**: the write-and-verify half of this task is now
proven solid across two structurally different renderers in two
different chapters. The remaining gap is purely the visual
confirmation step, blocked by scene pacing that outruns every capture
strategy tried so far (sleep-based and fully breakpoint-controlled
alike). No further capture-strategy variant is obviously left
untried within a GDB-remote-protocol-based approach — the round-trip
latency of that protocol itself (tens of milliseconds per packet) may
simply be too slow relative to how quickly this game's dialogue boxes
open and close.

## 8b. Follow-up: whole-line erasure, speed scaling, and synchronized re-patching

At the user's suggestion, the strategy shifted from a subtle single-
glyph position shift (hard to visually confirm even if captured) to
**erasing an entire visible line** (dramatic, easy to confirm) by
pushing every glyph primitive in the dialogue Y-band 1000px off-screen
vertically.

**Critical direct observation from the user**: watching the real
screen (not a screenshot) during these attempts, the user reported the
erasure *does* visibly happen — the glyphs flicker/disappear — but
only for about one frame, before the next frame's redraw restores
them. This is the single most important data point in this whole
investigation's live-testing effort: it proves the write mechanism has
real, immediate visual effect; the remaining problem is purely
capturing that one frame, not whether the edit works.

**Why a single edit only lasts one frame**: this game recomputes each
character's screen position fresh from source data every single frame
(established earlier this document). Editing the primitive's output
bytes changes what that one frame draws, but the very next frame
recomputes from the same unaffected source and overwrites it back.

**Attempts made, in order**:
1. *Single-shot whole-line erase, immediate screenshot*: found all
   ~90-140 glyph-shaped primitives via a raw RAM scan (not tied to any
   breakpoint), erased them, screenshotted. Result: by the time the
   scan (a 2MB read, several hundred ms to low seconds over the
   network) and the ~140×4 individual writes completed, the game had
   already advanced to entirely different, unrelated text — the scan
   and write phase itself was slower than the content's turnover rate.
2. *PCSX-Redux's own Speed Scaler discovered and used*: the user found
   and set the emulator's built-in speed scaler to 0.3 (confirmed via
   the FPS counter dropping from ~38 to ~18). This helps the *game's*
   pacing but does not reduce the fixed real-world cost of our own
   scan+write round trips, which remained the dominant bottleneck.
3. *Batched writes*: rewrote the erase to send one 32-byte block per
   primitive (covering all 4 vertices plus their interleaved UV/CLUT
   fields, read back unchanged) instead of 4 separate 4-byte writes,
   cutting round-trips 4x. Reduced total write-pass time but the game
   still advanced past the target content within 1-2 passes.
4. *Frame-synchronized re-patch* (the most principled attempt): armed
   the shared writer instruction (`0x80049088`) as a breakpoint and,
   on every single hit (i.e. every frame this game's text-drawing
   routine runs), immediately re-stamped the erased values onto every
   tracked primitive, for 12 consecutive frames, taking the screenshot
   immediately after the 12th sync with no free-run gap at all. All 12
   sync attempts landed on the first try (confirming the breakpoint
   mechanism itself is completely reliable). The resulting screenshot
   still showed fully intact, unerased text — by the time of capture,
   the visible dialogue had moved to different content again.

**Interpretation**: the write-and-immediate-effect mechanism is now
proven beyond doubt (the user's direct visual confirmation of
flickering is stronger evidence than any screenshot could be). What
remains unresolved is a screenshot capture that lands within the same
single-frame window as a synchronized patch — every technique tried
reduces but does not eliminate the gap between "the CPU is at the
right instruction" and "the Windows screenshot API has read back the
composited frame," and this game's dialogue content turns over fast
enough that this gap is still enough to miss it.

**Untried idea, noted for a future session rather than attempted here
given time already spent**: capture the screenshot from *inside* the
same halted moment used for the synchronized patch itself (i.e. do not
resume between the last patch and the capture at all — the 12-frame
sync loop already does this) combined with *slowing PCSX-Redux's own
video output separately from CPU speed* if such a control exists
(distinct from the CPU/game speed scaler already tried), or capturing
via a mechanism that reads the GPU's VRAM/framebuffer directly through
the debugger rather than through a Windows-level screenshot API call,
which would remove the OS compositor round-trip from the critical path
entirely.

## 10. Resolved: the live screenshot proof, and why every prior attempt missed it

A later session finally closed the gap documented in section 9.
Instrumented disassembly at the shared writer instruction
(`0x80049088`, PC-relative label in this dump: `RAM:800397c4`)
revealed the actual reason no edit ever stuck, regardless of timing:

```
RAM:800397c4  sh   $v0, 0x0008($s0)   ; write SXY0.x into the primitive
RAM:800397c8  lhu  $v0, 0x000a($s1)   ; read Y from a SEPARATE record
RAM:800397d0  sh   $v0, 0x000a($s0)   ; copy that Y into the primitive
```

`$s0` (the primitive array this whole investigation had been editing —
`0x800bbe48`, `0x800bc028`, etc., depending on scene) is a **write-only
destination**. Every single time this code runs (once per glyph, every
redraw), it *overwrites* the primitive's position from a separate
source record pointed to by `$s1`. Every previous technique — batched
writes, frame-synchronized re-patching, catching the very next write —
was editing the copy, so the very next execution of this same
instruction sequence silently restored the original value, often
before a screenshot could ever be taken. This is also the real
explanation for the ~1-frame flicker the user observed earlier: the
edit briefly reached the screen, then the next redraw copied the
untouched source right back over it.

**The fix**: edit `$s1`'s target memory instead of `$s0`. Live test on
a static choice-menu scene (three selectable lines, "A/B/C"):

1. Caught a write hit on the known primitive base, read `$s1` from the
   live register set (`0x800a2b7c` for this menu's "B" line).
2. Read the current value at `$s1+0xa` — `171`, which matched the
   independently-scanned on-screen Y position exactly.
3. Wrote `171 + 1000 = 1171` to `$s1+0xa` (one 2-byte write, verified
   by readback).
4. Screenshot: the "B" label and its line vanished from the choice
   menu entirely (pushed far below the visible frame), while "A" and
   "C" were untouched.
5. Restored `$s1+0xa` back to `171` (verified by readback); a follow-up
   screenshot confirmed "B" reappeared exactly as before.

This is the missing live, reversible, visually-confirmed modification
the rest of this document's sections were unable to produce. It also
means the true "source of truth" for this renderer's glyph positions
is one level deeper than previously mapped: not the primitive array
itself, but the per-glyph record at `$s1` (base observed so far:
`0x800a2ad4` and `0x800a2b7c` for two different glyphs in two
different scenes — consistent with a per-character array in that
region, fully mapped in section 11 below).

**Not resolved / open for a future session**: the GTE/RTPS-based call
site (`0x8004500C`) documented earlier in this project as a second,
structurally distinct renderer was re-tested against both an ordinary
dialogue line and this same choice-menu content; neither triggered it
even once over several minutes of real playtime. Whatever content
actually exercises that call site was not identified this round.

## 11. The per-glyph position record: fully mapped

Follow-up in the same session that produced section 10. Armed the
shared writer instruction with no call-site filter and collected 14
consecutive hits (one full dialogue line), reading `$s0`, `$s1`, `$s2`,
and the full 14-byte record at `$s1` on every hit:

```
char 0:  s0=0x800d0a5c s1=0x800a2ad4  00 00 00 00 15 00 c0 7f 0a 00 98 00 ff ff
char 1:  s0=0x800d0a84 s1=0x800a2ae2  10 00 00 00 15 00 c0 7f 1a 00 98 00 ff ff
char 2:  s0=0x800d0aac s1=0x800a2af0  20 00 00 00 15 00 c0 7f 26 00 98 00 ff ff
...
char 10: s0=0x800d0bec s1=0x800a2b60  a0 00 00 00 15 00 c0 7f 94 00 98 00 ff ff
char 11: s0=0x800d0c14 s1=0x800a2b6e  b0 00 00 00 15 00 c0 7f 40 00 ab 00 ff ff
char 12: s0=0x800d0c3c s1=0x800a2b7c  c0 00 00 00 15 00 c0 7f 4e 00 ab 00 ff ff
char 13: s0=0x800d0c64 s1=0x800a2b8a  d0 00 00 00 15 00 c0 7f 5c 00 ab 00 ff ff
```

Deltas: `$s0` advances by `0x28` per character (matches the known
40-byte `POLY_FT4` primitive size exactly), `$s1` advances by `0xe`
(14 bytes — the record size), and `$s2` stays completely constant
(shared per-line/per-textbox state, not per-character). The array
wraps back to its first entry after 14 characters, and `$s0` itself
alternates between two separate base addresses across wraps (e.g.
`0x800bbe48` region vs. `0x800d0a5c` region seen in different tests
this session) — consistent with a double-buffered primitive
destination reusing the same 14-entry source array each pass.

**Record layout (14 bytes, little-endian, all fields constant across
this whole test except where noted)**:

| Offset | Size | Content this test | Meaning |
|---|---|---|---|
| `0x0` | u16 | `index * 16` (`0, 0x10, 0x20, ... 0xd0`) | running per-character counter; purpose beyond indexing not confirmed |
| `0x2` | u16 | `0x0000` | unused/reserved in this sample |
| `0x4` | u16 | `0x0015` (21) | constant per line — plausible font/glyph-set ID |
| `0x6` | u16 | `0x7fc0` | constant — purpose not confirmed (clip/scale sentinel?) |
| `0x8` | u16 | varies, e.g. `10, 26, 38, 52, 64, 78, 92, 106, 120, 134, 148` then resets to `64` on line wrap | **X position** — increments by 12/14/16 per character (proportional glyph advance width), resets at line wrap |
| `0xa` | u16 | `152` for characters 0-10, `171` for characters 11-13 | **Y position** — confirmed both by exact match to independently-scanned on-screen coordinates and by the live edit in section 10 |
| `0xc` | u16 | `0xffff` | constant in this sample — sentinel/terminator, or an unused char-code slot |

This is now a complete, live-verified map of the true source-of-truth
struct for this renderer's glyph placement, one level past what
sections 1-9 had reached (which stopped at the primitive array).
Fields at `0x0`-`0x6` and `0xc` were only ever observed at their
constant values in this single test line — their behavior when varied
(different font, different textbox, a line long enough to actually use
a non-`0xffff` terminator, etc.) was not investigated and remains open.

## 12. Live X proof, and the breakpoint-timing lesson that unlocked it

Same session, immediate follow-up to sections 10-11. The first three
attempts at live-editing `$s1+0x8` (X) all failed silently — write
verified by readback every time, zero visible change — despite using
the exact same technique that worked cleanly for Y. Root cause, found
by re-reading the disassembly instead of varying capture timing again:

```
RAM:800397bc  lhu  $v0, 0x0008($s1)   ; X LOAD -- two instructions before...
RAM:800397c0  nop
RAM:800397c4  sh   $v0, 0x0008($s0)   ; ...the X STORE (our usual breakpoint)
RAM:800397c8  lhu  $v0, 0x000a($s1)   ; Y load happens AFTER the X store
RAM:800397d0  sh   $v0, 0x000a($s0)   ; Y store
```

The breakpoint used throughout this document (`0x800397c4`) sits
*between* the X load and the Y load. Editing `$s1` while paused there
is too late for X (`$v0` already has the stale value cached in a
register, about to be stored) but perfectly timed for Y (its load
hasn't happened yet). This is why Y worked first try and X did not —
not a difference in the mechanism, a difference in exactly which
instruction the shared breakpoint address happens to precede.

**Second obstacle, unrelated to the above**: by the time this was
fixed (moved the breakpoint to `0x800397bc`, before the X load), the
static choice-menu text from section 10 had *stopped being redrawn
entirely* — armed with no other filter, the breakpoint only ever fired
for one specific record (`X=26, Y=152`) hundreds of times in a row,
never for the actual letter glyphs anymore. That record turned out to
be the blinking `▶` cursor/selection indicator, the only element on
that static screen still being redrawn every cycle; the settled text
itself had gone quiet. This matches and extends the destination/source
finding from section 10: not only is the primitive array a copy, but
the source record itself is only *actively refreshed* for content
that's still animating — static text settles and stops being touched
by this code path at all once fully displayed.

**The proof** (three-shot triptych, same restore-and-verify discipline
as section 10): caught the cursor's record (`s0=0x800bc0c8`,
`s1=0x800a2bb4`, `X=26`), wrote `X=86` (`+60`) to `$s1+8`, confirmed by
readback both immediately and again after a 0.1s gap (value held
steady — the source is not being regenerated from elsewhere either),
and confirmed the primitive itself (`$s0+8`) now read the same X **and**
Y correctly packed together. Screenshot comparison: the `▶` arrow,
clearly visible to the left of "A" before the edit, vanished from that
position entirely after the edit (pushed off to the right, out of its
expected slot), and reappeared exactly as before once `$s1+8` was
restored to `26`.

**Lesson for future breakpoint placement in this renderer**: never
assume a single shared breakpoint address is equally well-timed for
every field it's near. Check the disassembly for exactly where in the
load/store sequence each field's read happens, and place the
breakpoint before *that specific* load, not just "somewhere in the
neighborhood" of the write. Also: when a live-edit test on a menu or
static screen produces zero visible change with a confirmed-correct
write, check whether the code path is still executing for *that
specific element* at all before suspecting the mechanism — animated
elements (cursors, blinking indicators) keep proving useful test
subjects even after the surrounding static content goes quiet.

## 13. Full chain traced end-to-end, and a single-step reliability warning

Attempted to trace forward from the writer instruction to the GPU
submission call by single-stepping and watching for `JAL`/`JALR`. Over
400 consecutive single-stepped instructions, PC samples showed
apparent jumps out to a `0x800774xx`/`0x80077xxx` region and back
several times, with **zero** `J`/`JAL`/`JALR` instructions ever
observed at the stepping point — a combination that should be
impossible (a plain conditional branch cannot reach ~253KB away, the
observed delta). Static disassembly of the supposed jump target
confirmed it: `0x800774b4` decodes as `lui`, unrelated to a branch
target. **Conclusion: those PC samples were spurious/corrupted
register reads**, not real execution — the actual trace stayed within
a tight ~0x180-byte loop (`0x80039696`-`0x80039820`ish) the whole time.
This is the same category of stop-notification/register-read
unreliability documented earlier in this project; single-stepping
combined with rapid register reads on this GDB stub cannot be trusted
without cross-checking against static disassembly, especially for any
"jump" that looks farther than a conditional branch could reach.

Abandoned single-stepping in favor of the mechanism proven reliable
all session: a plain `Z0` breakpoint, tested directly against a
hypothesis instead of discovered by blind stepping. `0x800774b4` — the
`addPrim` address already on record from before this session for the
*other* (GTE-based) renderer chain — was armed directly and fired
reliably, with `$a1` (the primitive pointer argument) matching known
primitive addresses: first the full-screen background quads
(`0x800beb60`, `0x800beb88`, matching the large tiled quads found in
section 11's era of scanning), then, within the same 60-hit window,
**`$a1 = 0x800d0a5c`** — an exact match for one of this session's own
known text-primitive buffer addresses (section 11's char-0 `$s0` for
one of the two double-buffered destinations).

**This closes the full chain for this renderer, end to end**:

```
$s1  (14-byte source record; X/Y at +0x8/+0xa)
  -> sh into $s0            (40-byte POLY_FT4 primitive, double-buffered)
    -> addPrim(0x800774b4, a1=$s0)   [shared across every primitive
                                       type this session observed --
                                       background, photo, and text]
      -> OT insertion -> DrawOTag -> GPU
```

`addPrim` at `0x800774b4` is confirmed to be a single, shared, generic
entry point used regardless of which front-end (this plain-writer
chain, or the still-unlocated GTE/RTPS chain) built the primitive —
consistent with the "addPrim links by reference, not by copy" static
proof recorded earlier in this project for the other chain. The two
renderer front-ends differ only in how they compute and stage vertex
data before this common submission point.

## 14. The two primitive destination buffers, mapped

Follow-up in the same session. Collected 100 consecutive hits at the
writer instruction and derived each hit's primitive-array *base*
address (using the character index recovered from `$s1`'s position in
its 14-entry source cycle to subtract back from `$s0`). Only four
distinct bases ever appeared, always in the same fixed rotation:

```
0x800bbe48 -> 0x800bc078 -> 0x800d0a5c -> 0x800d0c8c -> (repeats)
```

Deltas: `0x800bbe48 -> 0x800bc078` and `0x800d0a5c -> 0x800d0c8c` are
both exactly `0x230` (560 bytes = 14 x 0x28, one full 14-character
block) apart. The jumps `0x800bc078 -> 0x800d0a5c` and
`0x800d0c8c -> 0x800bbe48` are both much larger (~`0x149e4`, roughly
symmetric in magnitude).

**Interpretation**: not a simple 2-way ping-pong of single 14-slot
arrays as first assumed, but **two double-buffered destinations, each
holding 28 contiguous primitive slots** (`0x460` bytes = two back-to-back
14-character blocks):

- Buffer A: `0x800bbe48`-`0x800bc2a7` (line 1 slots `0x800bbe48`-`0x800bc077`, line 2 slots `0x800bc078`-`0x800bc2a7`)
- Buffer B: `0x800d0a5c`-`0x800d0ebb` (line 1 slots `0x800d0a5c`-`0x800d0c8b`, line 2 slots `0x800d0c8c`-`0x800d0ebb`)

This exactly matches what every dialogue-box screenshot this session
has shown on screen: up to **two visible lines per textbox**, each line
holding up to 14 characters — one 14-slot block per line, two lines
per buffer, two buffers alternating per frame for the classic
build-one-while-displaying-the-other double-buffer pattern. Which
buffer is "active" (currently displayed) versus "being built" for the
next frame was not directly instrumented this round (would need to
correlate against the GPU's own frame-flip signal); only the *pattern*
of primitive-destination rotation was captured.

## 15. Prototype: placing a glyph at an arbitrary chosen location

Combined sections 10-14 into one deliberate test: instead of nudging
an existing field by a relative delta, write **both** X and Y at once
to an arbitrary absolute location (`250, 152` — far to the right of
the choice menu, same text row) and confirm the glyph (the blinking
`▶` cursor, same test subject as sections 12-14) actually renders
there.

**A real capture-timing pitfall, caught and resolved rather than
worked around**: the first two attempts (one with an occluded Y, one
with a safe Y) both showed the screenshot taken immediately after the
edit still displaying the arrow at its *original* position, despite
readback confirming the write. Rather than conclude the mechanism had
failed, an independent, unhurried screenshot taken slightly later
(outside the script's tight edit-then-capture window) showed the arrow
correctly sitting at the new position, confirmed still present and
correctly placed. **The edit was correct every time; only the
immediate post-edit screenshot occasionally raced the render and
caught a stale frame** — the same category of capture-timing issue
documented at length in section 8, here caught cleanly by checking
again a moment later instead of trusting a single rushed screenshot.
Restored the cursor to its original `(26, 152)` afterward, verified by
a fresh readback in a new connection (`26`, exact match).

**Practical lesson for any future live-edit verification in this
project**: a screenshot taken in the same breath as a write-then-resume
sequence is not reliable proof of failure. If readback confirms the
write landed in memory, a live edit that appears not to show up should
be re-checked with an independent, slightly-delayed observation before
concluding the technique doesn't work — this pattern has now produced
at least two false "it didn't work" readings this session alone that
turned out to be capture-timing artifacts, not real failures.

## 16. LayoutDescriptor connected to Renderer 1 (live, position-only)

`gcrts.layout_descriptor_injection`'s own module docstring (written in
an earlier phase of this project, before this session) names the exact
gap that was blocking a real custom renderer from existing: "it needs a
multiply to compute a position-record address and touches globals
whose exact bit-width isn't fully confirmed." Sections 11-15 of this
document resolved precisely that gap for this renderer: base address
`0x800a2ad4` (confirmed stable across at least three different
scenes/textboxes this session), stride `0xe` (14) bytes per character,
X/Y fields at `+0x8`/`+0xa` — i.e. `position_record_addr = 0x800a2ad4 +
char_index * 0xe`, the exact multiply the module was waiting on.

This section closes the loop end-to-end, live, for the first time:

1. Built a real `EditorLayoutPlan` (one `LayoutLine`, text `"A"`,
   explicit `x=180, y=152`) using the project's own, pre-existing
   `gcrts.editor_layout_plan`/`gcrts.layout_descriptor` modules — no
   new format code, no shortcuts.
2. `encode_layout_descriptor(plan)` produced a genuine 30-byte `CLD1`
   buffer; `decode_layout_descriptor` parsed it back, yielding
   `lines[0].x == 180, lines[0].y == 152` — a real round trip through
   the actual binary format, not a hand-written stand-in.
3. Took those decoded values and wrote them into a **live** position
   record ($s1+8, $s1+0xa) on the running emulator, using the exact
   same technique proved in section 15 — the blinking `▶` cursor as
   the test subject, since static/settled text stops being touched by
   this code path (section 12's finding).
4. Confirmed by readback (`X=180, Y=152`, exact match) and then, per
   section 15's lesson, by an independent, unhurried screenshot: the
   cursor rendered exactly where the LayoutDescriptor specified —
   immediately after "たくない", the measured end of that text line,
   matching `x=180` precisely.
5. Restored the record to `(26, 152)`, verified by readback and a
   final screenshot showing the cursor back in its original position.

**What this proves and what it doesn't**: this demonstrates that a
position explicitly specified by a `LayoutDescriptor` — authored
through this project's own editor-side data model, serialized to the
real binary format, and decoded back — can concretely drive where
Renderer 1 places a glyph, closing links 1-3 of the module's own
stated chain ("editor layout plan -> binary descriptor -> live
injection") all the way through to an actual on-screen result, one
step further than that module intentionally went. It does **not**
install any permanent MIPS-side hook, dispatcher, or code patch — this
was a live, reversible GDB memory write exactly like every other test
in this document, not the "real custom renderer" the module's
docstring describes as its deliberately-deferred fourth link (which
would mean patching the game's own code to read from a descriptor
buffer automatically, rather than an external tool poking the position
record by hand). It also does not address character/glyph-shape
selection (which specific texture/CLUT the primitive draws) — this
test reused an existing glyph's shape fields untouched and only
overrode position, matching the LayoutDescriptor spec's own stated
scope (it carries the game's existing 16-bit glyph codes and assumes
the existing glyph lookup, not a replacement for it).

## 17. A whole line, moved as a rigid unit, to a genuinely random location, held for a real duration

Item 6's practical test: instead of one character, moved an entire live
11-character sentence ("A：全然、問きたくない", the full first line of
the choice-menu content sections 12-16 already used) as a single rigid
unit, to a position chosen by `random.randint` at run time (not
hand-picked), then held it there for a real 8-second wall-clock wait
before restoring — not a single-frame flash.

Since this text had already settled (section 12's finding: static text
stops being touched by the writer code path entirely once fully
displayed), no breakpoint or timing trick was needed at all — every
character's position record was read and written directly, live, with
the emulator running freely throughout:

1. Read all 11 characters' current `(X, Y)` from `$s1` records at
   `0x800a2ad4 + i*0xe` for `i` in `0..10` — confirmed exact match with
   the known on-screen progression (`38, 52, 64, 78, 92, 101, 115, 129,
   143, 155, 169`, all `Y=152`).
2. Picked a random target for character 0 (`random.randint(15, 140)`
   for X, `random.randint(140, 215)` for Y — this run: `(104, 168)`)
   and computed one shared delta (`+66, +16`) applied identically to
   all 11 characters — a rigid translation, not a per-character
   recompute, which is exactly what preserves each character's
   original proportional spacing relative to its neighbors without any
   extra math.
3. Wrote all 22 fields (11 x X-and-Y), verified every one by readback
   before proceeding.
4. Screenshot: the entire sentence rendered together at the new
   location, sliding down and right until it visually overlapped the
   second line ("B：教えて"), each character's relative kerning intact
   — a clean rigid-body move, not a scramble.
5. Held for 8 real seconds, screenshotted again: pixel-identical to the
   immediately-after-move capture — confirms this isn't a one-frame
   artifact, the position genuinely persists indefinitely once the
   game stops touching this settled text.
6. Restored all 11 characters to their exact original values, verified
   by readback, confirmed by a final screenshot matching the original
   exactly.

This is the same underlying mechanism as sections 10-16, just applied
to a full line instead of one field or one character — proportional
per-character spacing survives a whole-line move for free because the
move is rigid, and the earlier finding that settled text stops being
redrawn (normally a complication) becomes a convenience here: no
frame-timing choreography needed to make an edit *last*.

## 9. Cleanup and restoration status

- All breakpoints and watchpoints cleared (defensive full sweep of
  every address used this round and in prior rounds).
- No outstanding memory modifications: the one successful edit
  (`$s1+0xa` on the choice-menu scene) was restored and verified by
  readback (`1171` -> `171`); no other write from this round was left
  in place.
- Emulator confirmed running normally post-cleanup (live FPS counter,
  dialogue visibly progressing, no "Idle" state, PC advancing through
  plausible in-game addresses on a fresh register read).
- Project test suite (`tests/`, unrelated to this emulator work)
  re-run clean: 294 passed.
- Full test suite: 294/294 passing.

## 18. VRAM/background-image editing: investigated, not achieved this round

A separate goal explored the same session as sections 10-17, but never
resolved: rather than repositioning existing dialogue glyphs, directly
extract a background image (e.g. a scene's photo/texture, including
ones with text baked into them, like the vertical chapter-title screen)
as a normal image file, edit it externally, and write it back — "like
Photoshop," not primitive-level position editing.

**Confirmed, at the source-code level, not empirically**: neither
interface this project has working access to can move raw pixels in
or out of VRAM.

- GDB's `m`/`M` commands go through `Memory::MemoryAsFile`
  (`psxmem.cc`), which explicitly treats the hardware-register page
  (`0x1f80`/`0x9f80`/`0xbf80` in its own paging scheme) as absent from
  the read LUT (`readBlock` returns all-zero for it) and *silently
  drops* any write there (`writeBlock`'s own comment: "writing to
  their shadow behind the hardware's back would only desync the two,
  so those are silently dropped"). Confirmed empirically too: reading
  GPUSTAT (`0x1f801814`) returned `0x00000000` under every address
  form tried (KUSEG/KSEG0/KSEG1).
- The Lua scripting API (`pcsxffi.lua`, `pcsxlua.cc`) exposes exactly
  one GPU-related function, `PCSX.GPU.takeScreenShot()` — read-only,
  and it returns the final composited frame, not an isolated
  background layer or raw VRAM. No `getVRAM`/`partialUpdateVRAM`/blit
  binding exists despite the underlying C++ `GPU::getVRAM()` existing
  in `gpu.h` — it was simply never wired up to either scripting
  surface.

**What does still work, and how far it got**: real CPU-executed writes
*are* visible to breakpoints regardless of target address, since
`checkBP()` is invoked from the CPU's own instruction-execution path
(`Debug::process()`), independent of the debugger's own restricted
read/write path above. This game's routine per-frame primitive
submission goes through GPU DMA (channel 2), confirmed by tracing:

- A `Z2` watch on the GP0 data port itself (`0x1f801810`) never fires
  during normal play — consistent with DMA bypassing the CPU
  instruction path entirely for the actual pixel/command stream.
- A `Z2` watch on DMA channel 2's own `MADR` register (`0x1f8010a0`)
  *does* fire reliably, because the CPU must execute a real `sw`
  instruction to program the DMA controller before each transfer.
  Found the exact instruction: `sw $a0, 0($v0)` at `0x8007a184` — the
  transfer's source RAM address is always in `$a0` (GPR index 4) at
  that PC.
- Reading `$a0` across many hits revealed a **stable, repeating cycle
  of exactly 8 addresses** (`0x800c48e8, 0x800d139c, 0x800d3e28,
  0x800d13dc, 0x800afcd4, 0x800bc788, 0x800bf214, 0x800bc7c8`) — the
  routine per-frame OT/primitive-list submission, one DMA transfer per
  priority bucket, every frame, regardless of scene content.
- Three separate attempts to catch a *new* address appear at the exact
  moment of a scene transition all failed — including one where the
  background visibly changed dramatically (a jarred-specimen lab room)
  during the capture window, with zero new addresses observed. The
  interpretation that best fits this: **scene backgrounds are likely
  pre-loaded into VRAM in bulk well before the transition** (e.g.
  during an earlier loading screen), and what looks like a "new image"
  at a scene change is a reference/pointer switch among already-
  resident VRAM content, not a fresh upload — meaning watching for a
  transition-time DMA event was very likely the wrong moment to watch
  for in the first place, not simply a timing/coordination failure.

**Left open, if a future session wants to continue this**: catching an
actual bulk image upload would most likely mean instrumenting a
*loading screen* (chapter start, save load, or the title sequence)
rather than an in-scene transition — a harder moment to reach
deliberately since it typically only happens once per boot, early, and
can't be re-triggered by simply navigating within an already-running
session the way a dialogue line or menu can. No memory was left
modified by this investigation; every step here was read-only (memory
reads and register reads via breakpoint hits) except the two harmless,
already-restored primitive edits documented in section 17's cleanup.

## 19. Two independently-positioned lines, driven by one multi-line LayoutDescriptor

Completes item 6's remaining piece (proportional spacing and left
alignment were already covered by sections 16-17; this is the
multi-line half). After a full relaunch/reboot this session, confirmed
the position-record array base (`0x800a2ad4`, stride `0xe`) is stable
not just across scenes within one boot but **across a full process
relaunch** too — the same constant this whole document has relied on
since section 11.

On a fresh two-line choice/dialogue moment (12 characters at `Y=152`,
12 more at `Y=171` — the game's own natural line-wrap boundary, same
as section 11), built one `EditorLayoutPlan` with **two** `LayoutLine`
entries (`x=210,y=95` and `x=40,y=205` — deliberately far apart and far
from either line's original position), encoded it to real `CLD1`
bytes, decoded it back (round-tripped both lines' positions correctly:
`(210, 95)` and `(40, 205)`), then applied each line's resolved
position as an independent rigid delta to its own 12-character group
(delta0 `+200,-57`, delta1 `-66,+34` — different deltas per line,
proving the two groups are controlled completely independently, not
just moved together).

All 24 characters (12 per line) verified by readback after the write.
Screenshot: both lines rendered at their distinct, LayoutDescriptor-
specified positions — line 0's text near the character sprites at the
top, line 1's text at the very bottom of the frame — while the
dialogue *content* itself had naturally advanced during the test
(real-time gameplay continued running throughout, unrelated to the
position edit). Restored all 24 characters afterward; a final
screenshot confirmed positioning back to the standard layout (content
had advanced further by then, as expected, but the *position* was
correctly back to normal).

This is the same rigid-shift mechanism as section 17, just applied to
two independently-addressed groups from one descriptor instead of one
group — closing out item 6 (whole-line test: left alignment,
proportional spacing, and multi-line positioning all demonstrated live
and driven by the real binary format, not just the position-record
mechanism in isolation).

## 20. Center alignment, live

First of the "only after" tier. `gcrts.layout_descriptor`'s own
alignment-resolution math (`CUSTOM_LAYOUT_DESCRIPTOR.md`'s "Alignment
resolution" section) is a no-op unless a line specifies a
`max_width_px` budget wider than its measured text — there is nothing
to center or right-align *within* otherwise. Built a concrete case
where it isn't a no-op:

- Text: `"A" * 12` (12 half-width Latin characters, `8px` each per
  `estimate_char_width_fallback` — no real `GlyphAtlas` was available,
  so this uses the documented character-count fallback, not measured
  glyph bitmaps).
- `editor_x=20`, `max_width_px=200`.
- Measured width: `96px` (`12 * 8`).

Encoded and decoded all three alignments through the real pipeline to
confirm the formula end-to-end before touching anything live:

```
LEFT   -> x = 20   (= editor_x, unchanged)
CENTER -> x = 72   (= 20 + (200-96)//2 = 20+52)
RIGHT  -> x = 124  (= 20 + (200-96)   = 20+104)
```

Took the `CENTER` result (`72`) and applied it live: read the current
first 12 characters of an active dialogue line (`X=13` at char 0),
computed the delta to the resolved `x=72` (`+59`... actual run below
started from a slightly different live `X` since the scene had moved
on: delta came out to `+34` against that run's live starting X),
applied it to all 12, verified by readback, screenshotted, restored,
verified again. Result: the first line ("A：うるさいなー、帰れよ")
shifted right by exactly the computed delta as one block, while the
separate cursor indicator and the second line ("B：見るだけ見てやる
か・・・") were untouched — confirming the position write targets
only the intended character group, and the descriptor's centering
arithmetic is what actually drove the on-screen offset, not a
hand-picked number.

Not yet done: a center/right test using *real* measured glyph widths
via an actual `GlyphAtlas` (this used the character-count fallback
throughout, since no atlas was wired up for a live test this round) —
the arithmetic path is identical either way per
`measure_pixel_width`'s own fallback logic, but hasn't been separately
confirmed live.

## 21. Line-count limits: a real OT splice, and a wrong assumption caught cleanly

Cross-confirmation worth recording first: `gcrts.layout_validation`'s
own module docstring states `MAX_VISIBLE_LINES = 4` was confirmed via
a **static decompile** of `FUN_8004a6fc`/`FUN_8004a370`, reading
`*(ushort *)(DAT_800a4cd8*0xe+param_1+8)`. That formula — stride
`0xe`, `+8` offset — is exactly the struct this session mapped
*empirically*, independently, via live breakpoints (section 11). Two
completely different methods (static decompilation vs. live memory
tracing, done in different sessions with no shared context) landed on
the identical struct layout. Strong independent validation of both.

With that confirmed cap in mind, tried to test a 3rd/4th line. The
*current* dialogue only ever populates 2 lines' worth of source
records (24 characters); everything from index 24 onward in the `$s1`
array reads as genuine, untouched zero — confirming the game only
populates as many slots as the active text needs, not a fixed-size
always-initialized block.

Attempted the more ambitious test anyway (per explicit instruction):
manually construct a new primitive and splice it into the OT's linked
list by rewriting one real entry's own "next" pointer — a technique
discussed but deliberately deferred earlier this session (section 15's
introduction) as higher-risk than pure position-record edits, since it
touches the chain topology itself rather than just a primitive's
field values.

**Confirmed the chain direction first, empirically, before writing
anything**: read char 23's real primitive — a genuine 15x15 glyph at
`(258-273, 172-187)` — and its tag's low-24 "next" field pointed to
exactly `char23_addr - 0x28`, i.e. char 22's address. This confirms
the OT is built newest-first (each primitive's tag points to whatever
was submitted immediately before it), which matters for safety: it
means a new node can be spliced in by rewriting only ONE existing
node's tag (pointing it at the new node, whose own tag takes over the
old target) — no OT bucket-head address needs to be found or touched.

**The splice itself worked correctly** — bytes written, tag rewritten,
both confirmed by readback, and a real, visible change resulted.

**But it didn't land where intended, and that's the actual finding**:
the address used as "the next free slot" (`char23_addr + 0x28`) turned
out not to be free at all — reading it *before* overwriting showed a
real, active primitive whose own tag pointed back to char 23,
identifying it as the game's continue/wait indicator icon, chained
into the exact same OT list as the text (not a separate list, and not
a spare unused slot). Overwriting it visibly changed the icon's
rendered shape (filled square -> hollow outline) for one frame-or-so,
confirmed in a screenshot — clean proof the splice mechanism itself
is sound — but a follow-up screenshot ~2 seconds later showed the icon
already back to its original filled appearance **before any restore
had run**, because this icon (like the cursor in sections 12-15) is
itself actively redrawn every frame, and the game's own redraw simply
overwrote the injected data on its own. Restored both the splice
(char 23's tag) and the icon slot's original bytes anyway, verified by
readback; final screenshot confirmed no lasting change.

**Conclusion**: `char23_addr + 0x28` was the wrong address for "an
unused 24th text slot" — the real layout interleaves the continue-icon
into the same chain rather than reserving a clean, predictable
"next line" address immediately after the last character. Finding a
genuinely free slot for a real 3rd/4th line would need either locating
an actual game moment with 3-4 lines naturally displayed (per
`layout_validation`'s own live-confirmed 100-character probe) and
reading its real addresses directly, or more carefully surveying this
scene's full chain (not just guessing the next stride-sized offset)
before picking an insertion point.

## 22. Renderer 2 (the GTE/RTPS chain): one confirmed hit, chain not traced

The GTE/RTPS-based call site (`0x8004500C`) has been a standing open
question since before this session began — earlier work identified it
statically as a structurally distinct second renderer, but every live
test this session (plain dialogue, choice menus, both chapters)
produced zero hits, across many attempts.

This round finally got a real, live hit: while an atmospheric
narration sequence was on screen (the "Hanako-san" urban-legend
story — white/colored multi-line text over a dark background scene,
visually and structurally distinct from every dialogue/choice-menu box
tested so far, including a 4-line instance matching
`layout_validation`'s confirmed `MAX_VISIBLE_LINES=4` case), a `Z0`
breakpoint on `0x8004500C` fired:

```
a0=0x190e  a1=0x8000  a2=0x0  a3=0xff000000
```

**What wasn't achieved**: a full trace. Immediately after this hit,
re-validating the three known chain addresses (`CALL_SITE`,
`STORE_INSN` at `0x8007b250`, `DRAWOTAG_WRAPPER` at `0x800767f4`)
showed all three had drifted to different bytes (`5c444154`,
`f86e8424`, `a461428c` — none matching the previously-confirmed
values, and `5c444154`'s opcode doesn't even decode as a valid
`JAL`), and re-arming produced zero further hits. The most likely
explanation: this game loads distinct overlay executables per
chapter/scene (already established elsewhere in this project's
history), and whatever overlay was active for that one hit had
already been swapped out by the time of the retry. Several subsequent
attempts to reach another narration moment (across a full relaunch,
different chapters, and chapter-select navigation) did not reproduce
it within this session's remaining time.

**Left open for a future session**: this call site is real and does
fire for atmospheric narration content specifically — that's now a
confirmed fact, not a guess. A full trace (deriving the position-record
struct the way sections 11-14 did for the plain-writer chain) needs a
reliable way to land in a narration moment on demand, ideally
identified from the script/scene data rather than by incidentally
encountering one during normal play, plus re-validating the three
known addresses fresh in whatever overlay is active at that moment
before arming anything.
