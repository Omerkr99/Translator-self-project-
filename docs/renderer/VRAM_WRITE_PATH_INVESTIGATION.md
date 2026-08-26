# VRAM Write Path: Tested, No Observable Effect (Negative Result)

First concrete investigation into Stage 5's "VRAM-write-path" blocker
(`docs/status/TOOLKIT_READINESS_AUDIT.md` §13,
`docs/overlay_engine/PS1_OVERLAY_RUNTIME_SYSTEM_DESIGN.md` §19) -- one
of two prerequisites (alongside a movie-time source) gating any
PS1-native movie subtitle work. Scoped as a standalone, non-destructive
experiment against real gameplay frames, independent of the game's own
disc content or any movie, per this project's rule of proving each
Stage 5 prerequisite individually.

**A real methodological mistake happened during this investigation and
is recorded here rather than smoothed over** -- see "A wrong claim,
caught and corrected before it was written down as fact" below. The
net result is a clean negative, not the dramatic positive first
suspected.

## What was already known

This project's own read of PCSX-Redux's real Lua bindings
(`src/core/pcsxlua.cc`'s `REGISTER` list -- `getCPUCycles`,
`getMemPtr`, `getParPtr`, `getRomPtr`, `getScratchPtr`,
`getRegisters`, `getReadLUT`, `getWriteLUT`, breakpoint/pause/reset
controls, `takeScreenShot`, save-state functions, `quit`) confirmed
there is **no VRAM write function exposed to Lua at all** -- only
`takeScreenShot` touches the GPU class, and `gpu.h`'s own
`partialUpdateVRAM(int x, int y, int w, int h, const uint16_t *pixels, ...)`
(a real write-capable virtual method) is never wired up to scripting or
any other externally-reachable interface. This is a genuine negative
result verified against the real current source, not an unexplored API
the way the pad-input blocker turned out to be
(`docs/tooling/PCSX_PAD_INPUT_BRIDGE.md`).

That leaves one other candidate: writing directly to the GPU's real
hardware I/O ports (GP0 command/data FIFO at `0x1F801810`) via
`GdbClient.write_memory`, the same mechanism this project already uses
for CPU RAM. The closest prior data point is
`docs/tooling/PCSX_REDUX_CAPTURE_PROTOCOL.md` section 10's finding that
GDB writes to the *SPU* MMIO range (`0x1F801xxx`) don't round-trip on
readback -- this doesn't automatically transfer to the GPU (GP0 is a
write-only FIFO on real hardware too, so a readback mismatch there
would be expected regardless), so it needed a real, separate test
rather than an assumption either way.

## The experiment

Against a real running instance (original, unpatched disc, loaded via
its `.cue`), paused via `GdbClient.interrupt()` at a moment
independently confirmed to show real, correctly-positioned game
content (`check_content.png`: the Sony logo, with the `(0,0,320,240)`
screenshot crop already known from this project's own Stage 4 work to
be the game's real display area). Issued a standard PS1 GP0(A0h) "Copy
Rectangle (CPU to VRAM)" command sequence as four separate
`write_memory(0x1F801810, ...)` calls: command word, destination
coordinate `(20, 20)`, size `16x16`, then 128 data words (a solid
white fill). All four writes reported success at the GDB protocol
level. A screenshot was taken immediately before (`sony_before.png`)
and immediately after (`sony_after.png`) the sequence, with the CPU
still paused throughout so no real game rendering could occur in
between.

**Result: `sony_before.png` and `sony_after.png` are byte-identical**
(confirmed by hashing both files, not by eye). No 16x16 white square,
no change of any kind, anywhere in the frame.

A second, earlier attempt (writing the same command sequence at an
even earlier pause point, while the screen was still solid black
during boot) also produced byte-identical before/after screenshots.

## A wrong claim, caught and corrected before it was written down as fact

The first pass at this experiment did **not** compare screenshots by
hash -- it compared them by eye across a longer sequence (pause, write,
screenshot, *resume*, wait, screenshot again) and saw the frame turn
into visual noise, then a solid green fill that persisted through a
Hard Reset. This was initially written up as "the write demonstrably
corrupts VRAM." Before committing that finding, a hash comparison of
the actual saved files showed `sony_before.png` and `sony_after.png`
(taken immediately before/after the write, CPU still paused) were
**already identical to each other** -- meaning the "noise" was present
*before* the write executed, not caused by it. Diffing further back,
the clean Sony logo (`check_content.png`) and the "noise" frame
(`sony_before.png`) were confirmed different -- so the transition from
clean logo to noise happened during the few seconds of normal
(non-paused) emulation between those two captures, from the game's own
rendering, unrelated to any write. Re-running the write sequence
against a freshly-booted instance later reproduced a very similar
noise pattern from a completely different boot path (a deliberately
malformed raw-`.bin`-without-`.cue` load) with **zero GP0 writes
attempted at all**, confirming this noise is a real, independent
phenomenon of this project's own test setup (plausibly a boot-time
transition effect, or the CD-ROM subsystem struggling with a
disc-format edge case) that has nothing to do with the VRAM-write
question this experiment was actually testing. The wrong conclusion
was caught and this document rewritten before anything was committed.

## Conclusion

**No observable effect from writing to `0x1F801810` via GDB was
found**, across two independent attempts, one of them verified
byte-for-byte against a frame known to correctly reflect real
on-screen content. This is consistent with -- and extends -- the
already-documented finding that GDB-issued writes to the `0x1F801xxx`
MMIO range don't reliably reach real hardware-emulation side effects
(previously shown for SPU registers, section 10 of the capture
protocol doc; now also checked for the GPU's GP0 port specifically,
rather than assumed).

## What this does NOT prove, and what's still needed

- Not ruled out: the command sequence itself could be wrong in some
  way GDB-specific (e.g., a real hardware bus write and a GDB memory
  write might not be handled identically by PCSX-Redux's GPU emulation
  even at the same address, if the emulator's debug-memory-write path
  bypasses the code path that dispatches to the GPU core entirely).
  This wasn't isolated from "GDB writes to this address range don't
  work at all" as a possibility.
- Not attempted: reading PCSX-Redux's own GPU/memory-dispatch source to
  determine definitively whether `0x1F801810` writes issued via its
  GDB stub are even routed to the GPU class at all, versus silently
  landing in a plain memory buffer with no listener. This is the
  natural next step if this path is revisited -- it would settle
  whether the negative result is "the mechanism doesn't work" or "this
  particular way of using it doesn't work."
- Not attempted: any alternative write mechanism (a DMA-channel-driven
  transfer instead of direct GP0 writes, or investigating whether
  PCSX-Redux's own C++ core has an unexposed internal function that
  could be reached some other way).

**This blocker remains open**, effectively unchanged from "no VRAM
write path has been proven" -- the Lua-API gap was already known; this
session additionally checked and ruled out the one other candidate
(direct MMIO writes via GDB) without success. Movie subtitle rendering
via a native VRAM write should not be attempted again without either
tracing PCSX-Redux's own source for how (or whether) `0x1F801810`
writes are dispatched, or finding a different write mechanism
entirely.
