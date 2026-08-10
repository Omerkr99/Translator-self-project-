# Frame Render Modes

Per-frame mode table for `FUN_800481b0` (the master render loop), built
from live capture (40 total hits across two rounds this session, at
breakpoint `0x80048490` inside `FUN_800481b0`'s own frame).

## The flag byte itself

**Address/mechanism**: NOT a fixed global — it's a byte at `sp+0x22` in
`FUN_800481b0`'s own stack frame, offset `+0x0A` within a larger output
buffer (`sp+0x18`) that `FUN_800481b0` passes as `a1` to
`FUN_80049168` — **the project's already-known script-bytecode decoder**
(confirmed in `gcrts.script_decoder`/`gcrts.render_paths` as the real
dialogue-decoding path). The flag is reset to 0 before the call
(`sb $zero,0x22($sp)` at `0x800483ec`), then `jal 0x80049168` at
`0x80048410` populates it as one of the decoder's own per-frame outputs.

**This means the "mode" driving position-record handling is literally
the script decoder's own event-classification output for whatever
happened in the bytecode stream this frame** — not an arbitrary
internal render-loop state. This ties directly into this project's
existing control-code taxonomy work (`gcrts.script_decoder`,
`gcrts.control_policy`) rather than being a separate mystery.

## Read/branch order (from `FUN_800481b0`'s own disassembly, `0x8004841c`-`0x80048550`)

```
flags = *(sp+0x22)
if flags == 0:       goto skip_everything          ; IDLE
if flags == 0x80:     special path (page/wait-for-input related)
else:
    if flags & 0x02 == 0:  goto skip_everything      ; NO_FRAME_CALL
    else:
        if flags & 0x10:    mode = 1                 ; RESET_MODE
        elif flags & 0x40:  mode = 3                 ; Y_COLLECTION_MODE
        else:               mode = 0                 ; WIDTH_MODE
    call FUN_80049f84(records_base, ..., output_array, shared_buffer, mode)
```

## Confirmed mode table (live data, this session)

| flags value | mode | classification | observed frequency (40 hits, 2 rounds) | confidence |
|---|---|---|---|---|
| `0x00` | — | IDLE (nothing to do) | not separately counted (loop skips before capture point in some paths) | MEDIUM |
| `0x02` | 0 | **WIDTH_MODE** — normal per-character reveal; `FUN_80048e18`'s downstream reads (`lh a3,8($s2)`) return values consistent with `char_width<<3` (52, 78, 115 observed) | 7/40 | HIGH |
| `0x04`, `0x08`, `0x20` | — | NO_FRAME_CALL (bit `0x02` clear — `FUN_80049f84` not invoked this frame) | 7/40 | HIGH |
| `0x12` (`0x10\|0x02`) | 1 | **RESET_MODE** — resets `DAT_800a4cd8` (the position-record index) to `-1` immediately after the call, at the ORIGINAL call site (`0x8004852c`, the first of the two `FUN_80049f84` call sites in `FUN_800481b0`) | 26/40 (by far the most common) | HIGH |
| `0x80` | — | PAGE_TRANSITION_CHECK — a separate branch entirely, calls `FUN_8004ac5c` (the same getter checked by `FUN_8004ab1c`'s validity-flag logic) | 0/40 (not observed live yet) | LOW (disassembly only) |
| bit `0x40` set, bit `0x10` clear | 3 | **Y_COLLECTION_MODE** — contains the loop confirmed by static disassembly to walk the position-records array and collect up to 4 valid lines' Y values | **0/40 — not caught live despite two dedicated attempts**, including one spanning a confirmed 4-visible-line textbox boundary | MEDIUM (disassembly-confirmed structure, live occurrence not yet observed) |

**RESET_MODE dominance (26/40 = 65%) was unexpected** and suggests this
flag combination fires far more often than "start of a new textbox" —
most likely on every whole-word or every-character boundary in normal
typing, given the very tight interleaving with `WIDTH_MODE` hits
observed (e.g. hit sequence 1,2,3,4,5 in round 2: RESET, WIDTH, RESET,
RESET, WIDTH). This wasn't fully explained and should not be assumed —
flagged as an open detail per the project's "no field until an
address/prologue match is verified as more than a name" standard.

## Y_COLLECTION_MODE: still not caught live after 120 total samples

**Three rounds this session — 20 + 20 + 80 = 120 total live
captures — produced zero `Y_COLLECTION_MODE` (mode 3) occurrences.**
One round was specifically timed around a live-confirmed 4-full-
visible-line textbox reaching its boundary and being advanced past. The
classification logic was re-verified against the disassembly (bit
`0x10` → mode 1, else bit `0x40` → mode 3, else mode 0) and confirmed
correct — this is not a scan-logic bug. Final distribution across all
120 hits: `NO_FRAME_CALL` most common overall, `RESET_MODE` a strong
second (dominant within the mode-active hits), `WIDTH_MODE` a smaller
share, `IDLE` rare, **`Y_COLLECTION_MODE` zero**.

Two explanations, neither confirmed:

1. The specific trigger condition is narrower than "4 lines are full" —
   perhaps it requires an ACTUAL compaction/scroll event (a 5th line's
   worth of new text arriving while 4 are still occupying slots, forcing
   the oldest to be evicted), which the observed "press to continue"
   page-clear might not be (that could go through the `flags==0x80`
   special path instead, which was also never observed live).
2. The sampling window (20 hits, driven by manual advancing) is short
   relative to how rarely this specific combination of script-bytecode
   events occurs.

**This is an open, unresolved gap — not a ruled-out hypothesis.** The
disassembled mode-3 logic (position-record validity-flag walk,
Y-value collection, 4-entry cap matching `MAX_VISIBLE_LINES`) remains
the strongest concrete lead for connecting the wrap function's Y cursor
to something screen-position-related, but it needs an actual live
occurrence — not just static confirmation — before further tracing
(consumer identification, live modification test) can proceed
meaningfully.

## GENERALIZATION: same mechanism confirmed in a SECOND overlay (chapter 1)

A later session round found that switching to chapter 1 loads a
genuinely different overlay executable (every previously-traced address
held completely different code/data — the hook-site sanity check broke,
and `FUN_80049168`'s old address no longer decoded as the decoder at
all). Rather than treat this as invalidating the finding, the decoder
was RELOCATED for this overlay: a search for its address-independent
prologue bytes found no exact match (register allocation can differ
across separately-linked overlay builds), but a semantic search for the
family-mask/subtype-mask instruction pair (`andi ...,0xC000` followed
16 bytes later by `andi ...,0x3F00` — the exact same relative offset as
chapter 0) found exactly one candidate pair, which a full disassembly
dump confirmed was byte-identical compiled code to chapter 0's decoder,
just relocated:

| Chapter 0 | Chapter 1 | Meaning |
|---|---|---|
| `0x80049168` | `0x800398A4` | decoder entry |
| `0x80049240` | `0x8003997C` | word-consumption `lh` |
| `0x80049468` | `0x80039BA4` | flags store (`sb`) |
| `0x800A4CEA` | `0x800A39EE` | cursor global |
| `0x80048490` | `0x80038B54` | render-loop flags read |
| `0x801FE800` | `0x801FE800` | script buffer (**unchanged — confirmed shared/fixed**) |

The exact same two-stage breakpoint test (inject `0x8501` at the fresh
cursor address, confirm the load, confirm the flags write) was rerun
against these new addresses and **fired on hit 1 for both stages**,
identical to chapter 0's result. The render-loop dispatch breakpoint
(new address) also caught `Y_COLLECTION_MODE` live on hit 1. **This
confirms the trigger mechanism is genuine shared engine behavior, not
an artifact of one specific overlay's compiled code** — a meaningfully
stronger result than chapter 0 alone.

The non-empty-Y-list gap remains open in chapter 1 too: locating the
`FUN_80049f84` equivalent's exact call site required decoding JAL
targets from the dispatch region (candidates `0x800390E8` and
`0x8003A6C0`), and while a breakpoint at `0x8003A6C0` did catch our
target call once (`a3=0x801FFD58`, matching the expected per-frame
stack buffer, `ra=0x80038CA8`), a follow-up attempt to deliberately
land ON that specific return address found it drowned out by a much
higher-frequency, unrelated caller of the same address (`a3=0xFF000000`,
`ra=0x80039858`, firing on nearly every hit) — the target call is
comparatively rare and needs either a longer hit budget or tighter
timing around an actual multi-line scroll event to isolate reliably.
Not pursued further this round; state was left clean (cursor
unaffected, decoder bytes reverified intact) either way.

## FINAL: Y_COLLECTION_MODE caught live, full causal chain proven

A clean, low-latency injection (full breakpoint detail in
`DECODER_READ_CURSOR.md`'s "FINAL CONFIRMATION" and
`MODE3_TRIGGER_INVESTIGATION.md`'s corresponding section) closed the
entire chain in three linked live captures, each firing on hit 1 with
negligible elapsed time (no drift, no quickload):

1. Injected `0x8501` (`pause_flag_a`, nonzero parameter) at the exact,
   freshly-read decoder cursor address. Breakpoint at the consumption
   instruction (`0x80049240`) confirmed the word sat exactly where the
   decoder was about to read it.
2. A second breakpoint just past the flags write (`0x80049470`)
   confirmed the decoder wrote flags `0x42` as a direct result.
3. **A breakpoint at `FUN_800481b0`'s own flags-read point
   (`0x80048490`) confirmed `mode=Y_COLLECTION_MODE` on hit 1** — the
   render loop's OWN classification, not an assumption. This is the
   first live occurrence of mode 3 in this entire investigation, after
   120 natural-gameplay samples across earlier rounds caught zero.
4. Traced into `FUN_80049f84` itself (the mode-3 handler): broke at its
   entry, confirmed `ra=0x8004856c` (the second of the two known call
   sites) and `a3=0x801FFCE8` (the `sp+0x18` output buffer), then broke
   at that exact return address and re-read the buffer.

**Nuance found at this last step**: the buffer's contents were
unchanged before vs. after the call (`[23248, 32769, 18636, 32780, 0,
32834, 18636, 32780]` both times), because `valid_record_count` was 0
at the moment of this particular synthetic trigger — the position-
records array had no valid entries to collect, so the mode-3 loop had
nothing to write. This is expected, not a contradiction: a synthetic
control word injected without accompanying real multi-line dialogue
state naturally coincides with an empty records array. **The trigger
mechanism, branch, and mode classification are now fully proven live;
observing a genuinely non-empty collected-Y-list still requires
catching this same trigger while real position records are valid**
(e.g. during an actual multi-line textbox with active line records) —
this is the precise remaining step, not a new open question about the
mechanism itself.

## Update: exact trigger found, live occurrence still not confirmed

A full trace of `FUN_80049168` (the script-bytecode decoder) found the
**exact** producer of flags `0x42` (`Y_COLLECTION_MODE`): control word
family A, subtype `0x0500` (already named `pause_flag_a` in
`gcrts.control_position_risk`), with a **nonzero parameter byte**. Full
instruction-level trace in `MODE3_TRIGGER_INVESTIGATION.md`; reusable
matcher in `gcrts.control_code_index.produces_y_collection_mode`.

A synthetic injection test (minimal buffer containing `0x8501`) was
attempted twice via the guarded low-level write path — once during a
dialogue-free cutscene (inconclusive, never read), once during active
narration with careful pause/inject/resume timing (71 captures, still
zero `Y_COLLECTION_MODE` hits). The branch logic and loop-back
condition were re-verified against the disassembly after this null
result and confirmed correct — the most likely explanation is that the
game's script read cursor never actually reached the injected 20-byte
region during the observed window, not that the trigger hypothesis is
wrong. See `MODE3_TRIGGER_INVESTIGATION.md` for the full account.

A live scan of one real scene's script buffer (via the new
`gcrts.control_code_index` tool, see `SCRIPT_CONTROL_INDEX.md`) found
`pause_flag_a` occurring twice — always with parameter `0`, never
nonzero. This is positive evidence the code is real and not
astronomically rare; it just hasn't been observed with the specific
nonzero parameter needed, in the scenes reached so far.
