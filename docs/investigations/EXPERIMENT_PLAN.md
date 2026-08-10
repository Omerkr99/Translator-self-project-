# Experiment Plan — finding the real on-screen text-position source

## STATUS UPDATE 3: full mode dispatch mapped; candidate D found and left inconclusive (not ruled out)

Full detail now lives in two new dedicated documents:
`MASTER_RENDER_MODE_MAP.md` (organized by mode: 0/1/2/3 dispatch,
handler addresses, call sites, arguments, live-captured data for each)
and `VISIBLE_DIALOGUE_COMPOSITION_PATH.md` (organized by candidate
function: A/B/C/D, classification, evidence, and the precise next
task). Short version:

- Built a reusable, unit-tested `gcrts.mips_jal_decoder` (15 tests,
  294 total project-wide) specifically to stop the hand-arithmetic
  JAL-decoding mistakes that caused real delays this session — see
  `MIPS_JAL_DECODER.md`.
- Fully mapped the mode-handler's dispatch: modes 0, 1, 2 all
  live-captured with real arguments and flags correlation; mode 3
  confirmed by disassembly only this round (not re-triggered live).
- **Mode 2 naturally collects real Y-values** (152, 171 — 152
  independently matches the ORIGINAL chapter-0 investigation's own
  established Y constant) — finally resolving this session's
  long-standing "catch a non-empty Y-list" open item, without needing
  synthetic injection.
- Found and live-modification-tested two more candidates (mode 1's
  own `+8`/`+0xA` write, and mode 2's collected-Y array): both
  confirmed the modified value was still genuinely active at
  screenshot time, and both showed **no visible effect** — real
  negative results, not timing artifacts.
- **Found candidate D (`0x8003AAAC`)**, in the master render loop's own
  post-handler processing (not inside the mode-handler at all) —
  writes the SAME records array `+8`/`+0xA` fields. Live-modification
  test was **inconclusive**: the value reverted before it could be
  observed, because this write is recomputed more frequently than the
  current modify→screenshot round trip can outpace. This is explicitly
  NOT a ruled-out result — see `VISIBLE_DIALOGUE_COMPOSITION_PATH.md`'s
  "Invalid Success" framing.

**Precise next task**: trace candidate D's own source struct
(`0x800A38D4`, offsets `+0`/`+2`) backward to find what writes it, and
test modifying THAT instead of the destination — a source value
written once per line/textbox (rather than recomputed every character)
should propagate through the next natural recomputation and stay
visible long enough for a reliable screenshot.

## STATUS UPDATE 2: candidate B isolated, a new nested candidate C found — both classified as cache/texture-prep

Continued directly from the round below. Two concrete outcomes:

**Bug found and fixed**: the "candidate B" address used below (`0x8003B1E4`)
was itself the result of a hand-arithmetic error decoding the JAL word
at `0x8003a90c` (`0x0c00ec89`) — the correct target is **`0x8003B224`**
(`target_field=0xec89`, `<<2=0x3B224`, not `0x3B1E4`). This is the same
*class* of mistake (JAL target/return-address arithmetic) already
documented multiple times this session — always recompute via Python,
never by hand under time pressure.

**Candidate B, corrected (`0x8003B224`)**: isolated successfully with a
much larger breakpoint budget (found on hit 15 of a 240s run, exact
`ra==0x8003A914` match). Turns out to be called with **`a0=0`** (a
literal constant, not a records-base pointer) — it reads fields `+4`/
`+6` from a *different* struct (`a1`, the mode-handler's own 3rd
argument) and returns a small computed value. Not obviously
position-related; role not fully characterized (possibly a width/
spacing lookup), but structurally it cannot be writing into the
position-records array itself since it's never given that array's base
address.

**New candidate found while investigating candidate A's own body**: a
previously-unnoticed nested call inside candidate A (`0x8003AFFC`)
itself, to **`0x8003B144`** ("candidate C"), called with the REAL
records-base pointer (unlike candidate B). Its body:
1. Masks a value with `0xC000` (the same family-mask shape used all
   session for control-word classification) to decide a branch.
2. Redoes the index×14 record lookup, reads record `+0`/`+2` combined
   with fields from its own 2nd argument's `+2`/`+8`/`+0xA` offsets,
   and assembles a **4-halfword local buffer on the stack** shaped
   exactly like `(X, Y, W, H)`.
3. Looks up an entry in a table at **`0x80090AE8`** — which is an
   *exact, independently-arrived-at match* for the external toolkit's
   (`CURRENT_SYSTEM_STATUS.md` §0) confirmed `cap1.ini` `fonttbl`
   address for `CAP1.EXE` — strong cross-validation that this really is
   chapter-1's font/glyph-table lookup, not a coincidence.
4. Calls two external routines in sequence, the second (`0x800774CC`)
   receiving the assembled `(X,Y,W,H)` buffer as its argument — this
   profile's equivalent of the old `0x800786b8` GPU-upload call.

**Live-tested**: broke right before the second external call consumes
the buffer, read it — **`X=328, Y=320, W=4, H=16`** — exactly the same
fixed-stride, off-screen-range shape (`X=320+`, `W=4`, `H=16`) already
documented and ruled out for `FUN_8004aa08` in the original
investigation. Modified `X` to 200 and let the frame render:
**no visible change whatsoever** in the live dialogue text (confirmed
via screenshot — text rendered perfectly normally). Restore of the
buffer's stack slot itself came back mismatched on readback (the
transient local variable had already been reused by later, unrelated
calls by the time of the restore write — confirmed harmless: emulator
responsiveness re-verified clean afterward, no crash, no lasting
effect, since a stray write to an already-superseded stack slot doesn't
persist).

**Updated classification: `0x8003B144` (candidate C) is also
glyph-cache/texture-preparation, not the live screen-position writer**
— independently re-confirms the original `FUN_8004aa08` ruling in a
second, differently-compiled overlay, via its own from-scratch-derived
address chain.

**Where this leaves the search**: the two "common path" calls from the
mode-handler's WIDTH_MODE branch (candidate A → nested candidate C, and
candidate B) are now BOTH classified as cache/texture-prep or
position-unrelated. **The real draw call was not found in this common
path at all.** It must be either (a) inside one of the mode-handler's
OTHER, earlier branches (the mode==1/mode==2 dispatch paths near its
entry, `0x8003a708` onward, not yet traced), or (b) in a function this
whole per-character path doesn't call at all — matching the master
render loop directly, or a completely separate chain. This is now a
narrower, better-scoped open question than at the start of this round,
but still open.

**Precise next task**: disassemble and live-trace the mode-handler's
`mode==1`/`mode==2` branches (distinct from the `mode==0` WIDTH_MODE
path already fully traced) — these were seen firing live (registers
dump from earlier this round showed real mode=1 and mode=2 hits) but
never followed. If those also dead-end at cache/texture functions, the
search must broaden to the master render loop itself
(`FUN_800481b0`-equivalent, i.e. whatever currently calls the
mode-handler at `0x80038ca8`/`0x80038c60`/`0x80038c08`) as a hook point,
rather than continuing to chase per-character callees.

## STATUS UPDATE 1: 0x800786b8 caller-scan round — real progress, still open (see also DIALOGUE_GPU_PACKET_MAP.md, INDIRECT_RENDER_TARGETS.md)

A focused round targeting `EXPERIMENT_PLAN.md`'s own "scan for other
callers of `0x800786b8`" next step. **Key finding before any scanning
could even start**: `0x800786b8` (and every other absolute address
this call chain was previously documented against — the wrap function,
`FUN_8004a8c0`, `FUN_8004aa08`) is **not valid for the currently-loaded
profile**. The game's code layout drifted at least twice during this
one round, without any quickload: first from the "shifted" layout this
project's prior `MIPS_PATCH_PLAN.md` work was based on, to the
"original" layout (previously documented as 0-for-3, never observed
firing), and later to a layout matching this session's own
independently-mapped **chapter-1 overlay** (`gcrts`-external addresses
from earlier this session: decoder entry `0x800398A4`, cursor
`0x800A39EE`, render-loop dispatch `0x80038B54`) — reached mid-session
during ordinary "auto-transitioning" dialogue, not a reload. This is a
new, stronger form of the already-documented overlay-variance risk:
layout can drift **within a single loaded scene**, not just across
chapter/quickload boundaries. A literal "scan for callers of
`0x800786b8`" is meaningless until the CURRENT profile's own equivalent
address is re-derived — which is what this round actually did.

**Re-derivation approach used**: rather than trust any stale address,
searched for the register-agnostic "index × 14" instruction signature
(`sll ×3; subu; sll ×1`, the same one already used successfully to find
`FUN_80049f84`/relocate the decoder) across the live code segment.
Found a tight, real cluster (`0x80071a10`-`0x80071c5c`) — but two
independent live-breakpoint tests (its apparent function entry
`0x8007190c`, and the exact multiply instruction `0x80071a10` itself)
**never fired across a combined ~250 seconds of confirmed, actively
auto-transitioning dialogue** (breakpoint mechanism itself was sanity
checked and confirmed working via a known-good address in between).
**Conclusion: this cluster is very likely an unrelated 14-byte-stride
structure** (inventory, save data, or similar) — a real, useful
negative result. Do not re-investigate this cluster without new
evidence.

**What actually worked**: traced forward LIVE from already-confirmed
chapter-1 infrastructure instead of guessing at addresses. Broke at the
render-loop dispatch (`0x80038B54`, already proven this session),
followed into the mode-handler function it calls (`0x8003A6C0` —
this session's chapter-1 equivalent of `FUN_80049f84`), and confirmed
it also handles the WIDTH_MODE (mode 0, routine per-character reveal)
case, not just the rare mode-3 scroll case already traced. Disassembling
its body live found two JAL calls made together near its common exit —
structurally matching the OLD "wrap-function + cache-populate" pairing:

- **Candidate A (`0x8003AFFC`)** — CONFIRMED, both structurally (does
  the index×14 record lookup, writes to record offsets `+0`/`+2` via an
  actual `mult`/`mflo`) and empirically (live-modified `+0`/`+2` to an
  extreme value: produced an isolated, disconnected corrupted-glyph
  artifact in the textbox, while all three lines of the actual live
  dialogue text rendered completely normally). **This is the current
  profile's equivalent of the already-ruled-out `FUN_8004a8c0`
  glyph-cache/texture-index write — RULED OUT again, independently,
  for this profile.**
- **Candidate B (`0x8003B1E4`)** — reached (confirmed via a direct
  breakpoint at its call site, `0x8003a90c`), but turned out to be a
  **commonly-shared utility function** called from many unrelated sites
  throughout the code (observed `a0` values were arbitrary-looking
  addresses in the `0x8001xxxx` range, not a records-base pointer) —
  our specific call from the mode-handler is one rare caller among many
  frequent, unrelated ones. Filtering by the correct return address
  (`0x8003A914` — corrected from an initial `+4` arithmetic slip,
  the same class of mistake already documented earlier this session)
  found **zero matching hits even across 200+ breakpoint hits**,
  confirming it really is rare, not a filter bug. **Not yet confirmed
  or ruled out** — this is the one precise remaining unresolved link.

**Precise next task**: repeat the `EXPECTED_RA=0x8003A914` filtered
capture at candidate B's entry (`0x8003B1E4`) with a much larger hit
budget (thousands, not hundreds) and more patience, OR find a way to
identify the SPECIFIC call from `0x8003a90c` more directly (e.g. a
watchpoint on the records-base argument register, or breaking at
`0x8003a90c` itself — already confirmed reachable — and single-stepping
the two instructions into the call rather than re-breaking at the
shared target). If candidate B also turns out to be a false lead once
finally isolated, the search must broaden beyond this one mode-handler
function entirely, matching this file's own already-stated fallback
(scan for other callers of the GPU-upload primitive, once its
per-profile address is known).

## Prior status: Y_COLLECTION_MODE caught live, full chain proven (see FRAME_RENDER_MODES.md)

The blocking item at the top of this file ("catch mode 3 live") is
**done**. Full account in `FRAME_RENDER_MODES.md`'s "FINAL" section and
`DECODER_READ_CURSOR.md`/`MODE3_TRIGGER_INVESTIGATION.md`'s "FINAL
CONFIRMATION" sections: a clean cursor-targeted injection of `0x8501`
was traced live through every stage — decoder consumption (breakpoint
at `0x80049240`), flags write (`0x42` at `0x80049470`), the render
loop's own mode classification (`Y_COLLECTION_MODE` at `0x80048490`),
and into `FUN_80049f84` itself (entry + return-address breakpoints,
`ra=0x8004856c`, `a3=0x801FFCE8`). Every step fired on hit 1, with
negligible elapsed time — no ambiguity, no quickload confound.

**Remaining step**: the buffer read after `FUN_80049f84` returned was
unchanged, because `valid_record_count` was 0 at that moment (no real
multi-line dialogue state backing the synthetic trigger). To see an
actual non-empty collected-Y-list, repeat this same injection while a
real textbox has 2+ valid position records active (i.e. mid-dialogue
with established lines, not right after a fresh textbox opens). This
is a "get better timing/context for the same proven mechanism" step,
not a re-open of the trigger question itself.


Current state: a confirmed mode table exists for the per-frame render
loop's flag-driven branch (`FRAME_RENDER_MODES.md`), built from 40 live
captures across two rounds. `WIDTH_MODE` and `RESET_MODE` are confirmed
live; `Y_COLLECTION_MODE` (mode 3 — the mode containing the loop that
collects up to 4 valid lines' Y-positions, `MAX_VISIBLE_LINES`-matching)
has NOT been caught live despite two dedicated attempts, one
specifically timed around a confirmed 4-full-visible-line textbox. This
is the explicit next target — everything downstream (Step 5's "who
consumes the collected Y list," Step 6's live modification test) is
blocked on catching this mode occurring at all.

## Update 2: exact decoder read-cursor formula found, precise injection still inconclusive

Full formula in `DECODER_READ_CURSOR.md`: `read_address = 0x801FE800 +
DAT_800a4cea * 2`, live-verified against real script data. This
explains why earlier injections (writing to the buffer's absolute
start) never worked. A corrected, cursor-targeted injection was
attempted, but revealed a NEW complication: the script buffer appears
to be dynamically refreshed/streamed, not filled once per scene — the
injected word may have been overwritten by this natural refresh before
the cursor reached it. Neither of the two candidate verification
globals (`DAT_800a4cf8`, `DAT_800a4ce4`) turned out to be reliable
signals.

**New precise next step**: use a live breakpoint (not pure polling) at
the exact word-consumption instruction (`0x80049240`), filtered
correctly this time (this round discovered the entry-point breakpoint
and the actual-read-instruction breakpoint require different filter
registers — `$ra` works at entry, but gets clobbered by an intervening
`jal` before `0x80049240`, so `$a2` saved at `sp+0x38` must be used
there instead). Inject at the cursor-computed address, then IMMEDIATELY
arm this breakpoint (minimizing the window for the buffer to refresh
out from under the injected word) and single-step to directly observe
the load register's value — this is the only fully unambiguous way to
confirm consumption, per the parent task's own Phase F requirement.

## Update: exact opcode found, still not caught live (see `MODE3_TRIGGER_INVESTIGATION.md`)

The exact script-decoder branch producing `Y_COLLECTION_MODE` is now
known precisely: control word family A, subtype `0x0500`
(`pause_flag_a`), nonzero parameter byte — full trace in
`MODE3_TRIGGER_INVESTIGATION.md`, reusable matcher in
`gcrts.control_code_index.produces_y_collection_mode`. A synthetic
injection attempt (writing `0x8501` into the live script buffer) did
not trigger it across 71 captures; the branch logic was re-verified
correct, so the leading explanation is the game's script cursor never
actually reached the injected content, not a wrong opcode.

**New concrete next step, before trying another injection**: trace
exactly how `FUN_80049168`'s own read-cursor (`s4+8` in its frame)
relates to the live script buffer's base address (`0x801FE800`) — i.e.
confirm whether writing to the buffer's absolute start actually resets
where the decoder resumes reading, or whether it has its own persistent
byte offset that a small write doesn't rewind. This was assumed (by
analogy with `gcrts.live_injection`'s already-proven "rewrite the whole
buffer" pattern) but not independently confirmed for a FRESH,
externally-forced small injection like this one. A single breakpoint
at `FUN_80049168`'s entry, reading the resolved read-cursor address
right before and right after a write, would settle this in one capture.

**Alternative, lower-effort path**: keep scanning more scenes with
`gcrts.control_code_index` (already proven to find real `pause_flag_a`
occurrences) for a NATURAL nonzero-parameter occurrence, avoiding the
injection-timing problem entirely. Every new scene reached in-game is a
free data point — accumulate into one running `ControlCodeIndex`
rather than re-scanning from scratch each time.

## Step 1 (current frontier) — catch `Y_COLLECTION_MODE` live

Two approaches, not yet tried:

1. **Longer, unbounded capture window.** The existing
   `mode_aware_capture.py` is capped at `MAX_HITS = 20` per run. Since
   `RESET_MODE`/`WIDTH_MODE` dominate (33/40 combined) and mode 3 may
   simply be rarer than assumed, running with a much higher cap (e.g.
   100+) across sustained, varied play (not just one textbox) is the
   most direct next attempt — no new hypothesis needed, just more
   samples.
2. **Target an actual scroll/compaction event specifically**, not just
   "4 lines full." The task's own framing distinguishes "4 lines
   visible" from "a NEW (5th) line arrives while 4 are already
   occupied, forcing eviction of the oldest." The screenshot captured
   this session showed exactly 4 lines with a "press to continue"
   prompt (▼) — which may route through the `flags==0x80`
   page-transition-check branch instead (also never observed live) or
   through a full textbox CLEAR (routing through `RESET_MODE`, which
   WOULD explain the 65% dominance — every fresh line/textbox reset
   dominating a short capture window). The scroll/compaction case may
   require a DIFFERENT scenario: a textbox that keeps adding lines
   WITHOUT a page-clear in between (auto-scrolling dialogue, if this
   game has any), which hasn't been identified or reached yet.

## Step 2 — once mode 3 is caught, trace the collected Y list forward (task Step 5)

`FUN_80049f84`'s mode-3 branch writes into a buffer whose address, per
this session's live capture, is `sp+0x18` in `FUN_800481b0`'s OWN
frame — NOT the `a3` buffer inspected at `FUN_80048e18`'s entry (that
turned out to hold `char_width`-shaped data in the captures obtained,
confirming the SAME memory serves different roles by mode, per
`TEXT_POSITION_SOURCE_PLAN.md`'s "major structural finding" section).
Once a live mode-3 hit is caught, immediately (same breakpoint hit)
capture:

- The buffer contents right after `FUN_80049f84` returns (should show
  small, Y-coordinate-shaped values, e.g. 100-250 range, not the
  pointer-fragment pattern seen in `WIDTH_MODE`/`RESET_MODE` hits).
- `FUN_800481b0`'s own return address / subsequent instructions to see
  what it does with `sp+0x18` next — does it get passed to another
  function, copied to a static structure, or read locally by
  `FUN_800481b0` itself for further processing?

## Step 3 — live modification test (task Step 6, unchanged acceptance bar)

Once a specific consumer and field are identified: break BEFORE
consumption, modify ONE Y entry only (not all four — the task
explicitly warns against this, since a whole-screen effect from
modifying multiple entries wouldn't distinguish "this Y list controls
line position" from "this Y list controls some OTHER frame-global
effect"), resume, screenshot, verify ONLY the corresponding line moved
and nothing else did, repeat at least once more.

## Known-good tooling to reuse, not rebuild

- `gdb_proper_client.py` (scratchpad) — fixed, working GDB client.
  Always send an explicit `c` right after `Z0` on a fresh connection.
- `mode_aware_capture.py` — mode-classifying frame capture, bounded at
  `MAX_HITS`; raise the cap for the next attempt rather than writing a
  new script.
- `glyph_event_capture.py` — bounded multi-hit JSON capture for
  per-character events; adapt `BREAK_ADDR` for a new function.
- The whole-code-segment JAL scan and the direct byte-pattern multiply-
  search (both used this session to find `FUN_80049f84` and its
  callers) — reusable for finding any other consumer once mode 3 is
  caught and its output buffer's next reader needs to be found.
- When an indirect call or JAL target's first argument is a fixed
  address, read what's stored there before concluding anything about
  the call's purpose (see `NOTES.md`'s "read the string, don't just
  read the shape" — this caught a debug-printf being mistaken for a
  GPU primitive submission).
- Window handle for screenshots: query by `MainWindowTitle -like
  "*PCSX*"`, not by the launcher process's own PID (that one reports
  handle 0).
- Multi-screenshot capture (5 frames, ~180ms apart) for ruling
  buffer-swap-timing explanations in or out before accepting a
  single-screenshot "no effect" result.
- When a live-modification test needs several seconds to observe
  propagation through a low-frequency copy (as with candidate D's
  source template), check whether the destination is a **shared,
  frequently-recomputed slot** (e.g. via an index/generation counter)
  before trusting any value read at the end of that window — ordinary
  unrelated activity can overwrite the same slot during the wait and
  produce a coincidental-looking but non-causal match. Prefer a tight
  chained-breakpoint sequence (modify at the source's own write site,
  single-step the consumer, screenshot within under a second) over
  sleep-and-poll whenever this is suspected. Confirmed this round: two
  sleep-and-poll trials on the same source/destination pair gave
  contradictory offsets (203 vs. 60, expected 63) once the index
  counter was checked and found to have advanced by 26 between them.
- `PrintWindow(hwnd, hdc, PW_RENDERFULLCONTENT)` is the only reliable
  screenshot method for this GPU-accelerated window; `GetDC`+`BitBlt`
  silently returns stale/cached frames, especially after a window
  resize, and produced a long run of falsely "frozen"-looking captures
  this project mistook for a real emulator freeze. Note the reverse
  caveat too: `PrintWindow` (and `BitBlt`) both return solid black if
  the target is genuinely CPU-halted at the very entry of a frame's
  `DrawOTag` call, before the GPU has rasterized anything for that
  frame — halt one `DrawOTag` invocation later instead.
- Never cycle `Z0`/`z0` per-iteration in a polling loop against this
  project's GDB stub — it reliably desyncs into a pathological
  alternating stale-hit pattern. Arm every breakpoint needed for an
  experiment once, then loop only on `continue`, checking the returned
  PC against the *set* of currently-armed addresses.
- This game has at least two structurally distinct dialogue-rendering
  code paths (plain conversation boxes vs. a portrait/photo-inset +
  choice-menu cutscene UI). A breakpoint proven reliable for one will
  produce persistent, correct-looking zero hits during the other —
  confirm the on-screen dialogue box's visual style via screenshot
  before treating "no hits" as a broken breakpoint. Full detail in
  `RENDERER_LIVE_PROOF.md`.
  **Update**: a later session found photo-inset and choice-menu text
  actually using the *same* plain writer as ordinary dialogue, not a
  separate renderer as this bullet assumed — see `RENDERER_LIVE_PROOF.md`
  section 10 for the correction and the unresolved discrepancy with the
  earlier test that seemed to prove otherwise.
- The single biggest reason a live memory edit never showed up on
  screen, across many sessions of otherwise-correct breakpoint/write
  technique: the primitive array being edited can be a **write-only
  destination**, refreshed from a separate source register every
  single cycle. Confirmed by reading the actual disassembly at the
  writer instruction rather than continuing to vary capture timing —
  it showed a `lhu` from `$s1` immediately followed by the `sh` into
  the primitive. No amount of synchronization trickery fixes this;
  the tell is an edit that reverts even when the screenshot is taken
  within the same halted moment as the write. Check the instructions
  immediately around any "write" breakpoint for a load from a
  different register first, before assuming the write target is the
  source of truth. Full account in `RENDERER_LIVE_PROOF.md` section 10.
