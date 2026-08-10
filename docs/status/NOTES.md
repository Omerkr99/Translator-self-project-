# Notes

A general running-notes file. Many existing modules under `gcrts/`
(`glyph_atlas.py`, `script_decoder.py`, `render_paths.py`,
`cdb_codec.py`, and others) reference `NOTES.md` as the source for
earlier findings (Phase 5/6 GDB confirmations, the `FUN_8007681c`
decompression discovery, the `K0LINK`/`KFONT` disc-format work, etc.).
**That file was not present in this repository when this note was
written** — those references point to a document that either predates
this repo copy or was never committed. This is flagged here rather than
silently worked around: do not assume its content without finding the
actual source, and do not fabricate historical findings to fill the
gap. The formal docs that DO exist and carry equivalent authority are
`BASELINE_REPORT.md`, `MEMORY_MAP_FINDINGS.md`, `MIPS_PATCH_PLAN.md`,
`TEXT_ENGINE_ARCHITECTURE.md`, `CUSTOM_LAYOUT_DESCRIPTOR.md`, and now
`TEXT_POSITION_SOURCE_PLAN.md`/`TEXT_POSITION_TRACE_LOG.md`.

## This session's thread: identifying the real source of dialogue text position

Full account in `TEXT_POSITION_SOURCE_PLAN.md` (status + pipeline map),
`TEXT_POSITION_TRACE_LOG.md` (row-by-row captured evidence),
`DIALOGUE_GPU_PACKET_MAP.md` (field-level map), and
`INDIRECT_RENDER_TARGETS.md` (indirect-call resolution). Short version:
three candidate mechanisms have now been disassembled and empirically
tested. Two position-record fields (the wrap function's cursor,
`FUN_8004a8c0`'s cache-populate fields) were ruled out via direct
memory modification + screenshot comparison. A third candidate — the
`FUN_8004aae8`/`FUN_8007ad74`/`FUN_8007acdc` chain, which looked like
real GPU primitive construction from its bit-packing shape — was fully
traced this round: its indirect call resolves (live-confirmed via
reading both the function pointer AND the string it references) to a
**debug-mode printf logging GPU tpage/clut/clip attributes**, not a
primitive-submission mechanism. A credible alternative this raised
(PS1 double-buffering placing the earlier-ruled-out cache write in a
currently-invisible back buffer) was tested via rapid multi-screenshot
capture and not supported. **The real screen-destination writer is
still not found** — all three investigated mechanisms are now ruled
out or reclassified as cache/logging/attribute-only, and the search
must broaden beyond this one call chain. See `EXPERIMENT_PLAN.md`'s
current "next experiment" for the precise next step (scan for other
callers of the GPU-upload primitive `0x800786b8`).

## Durable tooling fix worth remembering

The scratchpad's `gdb_proper_client.py` (a hand-rolled GDB
remote-protocol client, not part of the `gcrts` package) had two real
bugs that made every breakpoint attempt earlier this session time out:

1. It never sent the `+` acknowledgment byte after a reply, even though
   `qSupported`'s response shows ack-mode is on by default
   (`QStartNoAckMode+` is advertised as a togglable feature, not the
   default state).
2. A fresh connection's target starts halted and needs an explicit `c`
   sent right after `Z0` to actually run — the earlier assumption (a
   breakpoint's first hit "arrives on its own" with no continue needed)
   only holds for a connection that was already free-running earlier in
   the same session.

Both are fixed in the scratchpad copy. Any future breakpoint-based work
on this project should start from that fixed client, not re-derive the
protocol from scratch.

## The frame-mode flag is the script decoder's own output, not internal render-loop state

`FUN_800481b0` (the master render loop)'s mode-selection flag byte
(`sp+0x22` in its own frame) is populated by `FUN_80049168` — this
project's already-known script-bytecode decoder (see
`gcrts.script_decoder`/`gcrts.render_paths`) — as one of its own
per-frame return values. This means the "modes" driving position-
record handling are literally script-bytecode event classifications,
not arbitrary internal state invented by the renderer. Full mode table
in `FRAME_RENDER_MODES.md`. Two modes (`WIDTH_MODE`, `RESET_MODE`) are
now confirmed live; a third (`Y_COLLECTION_MODE`, mode 3) remains
disassembly-only — not caught in 40 live captures across two rounds,
including one deliberately timed around a confirmed 4-visible-line
textbox boundary. This is an open gap, not a dead end.

## The exact decoder read-cursor formula, and a newly discovered rolling-buffer complication

Full account in `DECODER_READ_CURSOR.md`. Short version: traced
`FUN_80049168`'s own word-fetch sequence and found `read_address =
0x801FE800 + DAT_800a4cea * 2` — live-verified against real script
data (small character-code values, a genuine `0xFFFF` terminator).
This explains why earlier synthetic injections (writing to the
buffer's absolute byte 0) never worked — the cursor was already well
past that position. A corrected, cursor-targeted injection still
didn't conclusively prove consumption: the injected word had reverted
to its pre-injection value (also coincidentally `0`) by the time the
cursor passed through, suggesting the script buffer is dynamically
refreshed/streamed rather than filled once per scene — a narrower,
more fragile injection timing window than assumed. Not claimed as
success or failure; the next attempt needs a live breakpoint at the
exact consumption instruction (`0x80049240`) rather than pure polling,
to unambiguously observe the load register at the moment of
consumption.

**Also worth remembering**: a JAL's return address is `PC+8` (after the
delay slot), not `PC+4` — an arithmetic slip this round that initially
made a correct breakpoint filter look like it was catching zero hits
from the expected caller.

## Y_COLLECTION_MODE (mode 3) caught live — full chain now proven

A clean retry (fresh cursor read immediately before injecting, per the
operator's explicit "reinject after any quickload" guidance) fired on
hit 1 at every stage: decoder consumption, flags write (`0x42`), the
render loop's own mode classification, and `FUN_80049f84`'s entry/
return. Full detail in `FRAME_RENDER_MODES.md`'s "FINAL" section. The
one remaining nuance: the collected-Y buffer read back unchanged
because there were 0 valid position records at that exact moment
(synthetic trigger, no real multi-line dialogue backing it) — the
mechanism is proven, seeing a genuinely non-empty Y-list just needs the
same trigger repeated during real multi-line dialogue state.

**Tooling lesson from this round**: single-stepping (`s`) directly at
an address where a software breakpoint (`Z0`) is still armed can
re-trigger the trap instruction instead of executing the real one
underneath it, producing garbage register reads. Fix: remove the
breakpoint (`z0`) before single-stepping past that address, or avoid
single-stepping entirely by chaining a SECOND breakpoint a few
instructions further along and reading memory normally after it fires
(what the final successful version did).

## The exact mode-3 trigger opcode, and why it hasn't fired live yet

Full account in `MODE3_TRIGGER_INVESTIGATION.md`. Short version: traced
`FUN_80049168` (script decoder) to find the exact branch producing
`Y_COLLECTION_MODE` — control word family A, subtype `0x0500`
(`pause_flag_a`), nonzero parameter byte. Built a reusable index tool
(`gcrts/control_code_index.py`) to search real script data for
occurrences; found `pause_flag_a` is real (2 occurrences, one scene)
but always parameter-zero so far. A synthetic injection test (writing
`0x8501` directly into the live script buffer via the low-level guarded
write path, bypassing `live_injection`'s own filtering which drops this
code for edited units) did not trigger the mode across 71 captures —
re-verified the branch/loop-back logic is correct after the null
result, so the leading explanation is a script-cursor timing mismatch
(the injected content may never have actually been read), not a wrong
opcode. This remains open.

## A resolution technique worth remembering: read the string, don't just read the shape

Bit-packing that LOOKS like GPU tpage/clut/CLIP encoding is not proof
of a primitive-submission path — this session found real such packing
that turned out to feed a **debug printf**, not a draw call. The
technique that caught this: when an indirect call's first argument is
a fixed, hardcoded address (not a computed value), read what's actually
stored there before concluding anything about the call's purpose. A
plain `read_memory` + `.decode()` settled in one step what days of
further disassembly might not have. Apply this whenever a call site
passes a suspicious fixed address as an argument.

## A live-testing methodology bug worth remembering too

When testing "does modifying field X change what's on screen," the
breakpoint must fire BEFORE the consuming function reads that field —
not after. Breaking at a function's *return* point (after it already
called the actual GPU/blit primitive) means any modification only
affects a future reuse of that memory, not the frame already rendered.
This produced two false "no effect" results before being caught and
corrected (see `MIPS_PATCH_PLAN.md`'s "Empirical confirmation" section
for the full account). Any new live-modification test should break at
the entry of the function that CONSUMES the field, not after.
