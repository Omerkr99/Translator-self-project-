# Memory Map Findings — Alternative Text Engine, Phase 5

Per the master prompt's section 13 ("Memory Strategy") and Phase 5
("Memory research... Produce: MEMORY_MAP_FINDINGS.md"). This consolidates
work from two sessions: an earlier, separate investigation (before this
master prompt's phase plan started, recorded in NOTES.md's "Scoped (not
implemented): replacing the wrap mechanic entirely with custom code"
section) and new work done specifically for this phase.

**Update (Phase 7)**: a candidate found after this document's original
two failures — `0x801a0000`, a 30,720-byte zero run — was confirmed safe
across two independent rounds of real gameplay, then successfully used
to hold a live 12-byte stub patch that has been installed, executed on
every dialogue render since, and verified producing zero visible
regressions. See `MIPS_PATCH_PLAN.md`'s "Phase 7" section for the full
account. **This is still a per-session finding, not a permanent one** —
confirmed safe for THIS run, not yet re-verified after a reload/restart
or against any of the other ~9 overlay executables. No PERMANENT memory
region is confirmed safe; this is exactly the master prompt's
development-only exception (13.5), used as intended.

## 13.1 — Static executable slack: two candidates tested, both ruled out

Both tests used a live-write marker methodology: write a harmless true
MIPS no-op pattern (`sll $zero,$zero,42`, bytes `80 0a 00 00` — safe even
if the region turns out to be executed, since writes to `$zero` are
discarded) into a candidate zero-byte region, have the operator play
through real gameplay, then read back to see if the game overwrote it.

1. **`0x800a3d00`–`0x800a3d9c`** (156 bytes, adjacent to a "stale/reset"
   layout struct at `0x800a3dd0` noted during the text-wrap investigation):
   marker was fully erased (back to all zeros) after normal play —
   confirmed an actively-used scratch buffer.
2. **`0x801feb3c`–`0x801ff000`** (1220 bytes, immediately after the
   current scene's script content in the script buffer): marker was
   overwritten starting from byte 0 after advancing through more
   scenes — confirmed live script-buffer space a longer script fills
   into. This one was correctly predicted as risky by reasoning alone
   (it's plainly part of the script buffer's own reserved region) before
   being confirmed empirically.

Memory map for reference (from CAP0.EXE's own declared segments):
```
CODE: 0x80045000 - 0x800a3fff (~386 KB)
RAM:  0x800a4000 - 0x801fffff (~1.3 MB) -- a mix of live data structures
      already mapped by this project (layout struct, position-records
      array, the script buffer at 0x801fe800), NOT a free pool.
```

## 13.2 — Stack headroom: attempted, hit a real measurement limitation

Read the live register set via GDB's `g` packet (a single safe read, no
breakpoint, no continue — no freeze risk). Confirmed the register layout
is standard MIPS-GDB order (32 GPRs + sr/lo/hi/bad/cause/pc + 32 FPRs +
fsr/fir = 72 registers, 288 bytes) by checking `zero` reads as `0` and
`sp`/`ra` land in the expected RAM range.

Baseline reading: **`$sp = 0x801ffd90`**, **`$fp = 0x801fff00`**. The
stack lives at the very top of RAM (`0x801fffff`) and grows downward, as
expected — only ~623 bytes in use at this idle moment.

**Sampled again after the operator advanced through more dialogue: the
identical value, `0x801ffd90`.** This is itself the finding, not a null
result: point-in-time sampling between user actions can only ever catch
the game's steady-state IDLE depth, because that's the only moment slow
enough for a human-paced "act, then read" cycle to land in. Whatever
deeper stack usage happens *during* a few milliseconds of actual
rendering is invisible to this technique entirely.

Measuring real PEAK stack depth would require a breakpoint at the exact
instant of deepest call recursion — which reintroduces the exact freeze
risk documented in the earlier custom-mechanic investigation (rapid
breakpoint/continue cycling reliably left the emulator stuck), for a
task where four prior breakpoint attempts already failed to produce any
usable data. Given that pattern, this was not attempted again here.

**Conclusion**: stack headroom is NOT established as safe. Per the
master prompt's own explicit rule ("Do not use stack space as persistent
storage... may be used only after measured proof of safety"), it
couldn't be used for permanent storage anyway — and "measured proof of
safety" specifically hasn't been achieved. A genuinely different
technique (e.g. instrumenting the game's own code to record a low-water
mark over time) would be needed, and that itself requires safe memory to
install into — a circular dependency this investigation can't resolve
from the Python/GDB side alone.

**One real safety observation worth flagging regardless**: the script
buffer (`0x801fe800`) sits only ~7.3 KB below the observed idle `$sp`
(`0x801ffd90`). If some heavy operation's stack usage ever exceeded that
headroom, it would risk corrupting the script buffer. No evidence either
way on how close real gameplay gets to that — this is a flagged risk to
be aware of, not a confirmed problem.

## 13.3 — Overlay-specific memory: confirmed to be a real concern, not investigated further

This game has at least 10 overlay executables:
```
CAP0.EXE  391,168 bytes
CAP1.EXE  452,608 bytes
CAP2.EXE  434,176 bytes
CAP3.EXE  454,656 bytes
CAP4.EXE  454,656 bytes (identical size to CAP3 -- not confirmed identical content)
CAPX.EXE  389,120 bytes
```
plus several character-named executables (`MYOKO.EXE`, `MRIKA.EXE`,
`MNINO.EXE`, etc.) that plausibly correspond to the 5 structurally
identical narrative call sites found in the earlier blast-radius
investigation (one overlay per playable character/scenario, in this
multi-protagonist game).

Every size differs (except CAP3/CAP4, unconfirmed whether that's
coincidence or a genuine duplicate) — these are confirmed to be
genuinely different compiled executables, not copies. **Both memory
candidates tested above were only ever verified against whichever
overlay (CAP0.EXE) was loaded during that specific test.** A region's
exact address, or even its existence as "the same kind of scratch
buffer," is not established to hold in any of the other 9 executables.
Per the master prompt's own explicit caution: "A region safe in one
overlay may be unsafe in another." Testing across all of them was not
attempted this phase — a real, bounded follow-up if this line of work
continues (repeat the same live marker-write methodology once per
overlay, which requires triggering each character's scenario in-game).

## 13.4 — Reusable existing buffer

The script buffer's own tail (tested in 13.1, candidate 2) was the one
concrete instance of "does an existing buffer have safe slack past its
active region" investigated so far, and it came back negative — the
region isn't safely reusable, since a longer script fills into exactly
that space. No other existing buffer (e.g. a glyph-decompression staging
area) has been investigated for spare capacity.

## 13.5 — External emulator-assisted patching (development-only)

Not implemented, but worth recording as the master prompt explicitly
frames this as acceptable for development/preview: since PCSX-Redux's GDB
remote stub allows writing to any live RAM address (already exercised
extensively this project — every text injection is exactly this), a
development-only workflow of "write a routine to some address known to
be safe for THIS SPECIFIC RUN (verified live, right before use, via the
same marker-write check), reinstall on every executable reload" remains
viable in principle. It was not pursued because no address has yet been
confirmed safe even for a single run in a bounded way, and building this
lifecycle machinery before that foundation exists would be solving the
wrong problem first.

## 13.6 — Executable expansion or relocation (final disc build)

Not investigated. This is explicitly final-build scope per the master
prompt ("Do not implement this until the loader and executable format
are understood and tested"), and nothing in this project has looked at
how `.CDB`/disc loading actually maps these overlay executables into RAM
at the file-format level yet.

## Overall conclusion

**No memory region is confirmed safe for a permanent code cave.** Two
candidates were tested rigorously and ruled out; stack headroom hit a
real measurement-technique limitation rather than being ruled in or out;
overlay-specific variance is now confirmed to be a real, not theoretical,
concern given 10 differently-sized executables exist. Per the master
prompt's own instruction ("Do not claim a memory region is free without
live evidence... If no safe memory region exists, stop MIPS
implementation and report the evidence. Do not guess."), Phase 6 (MIPS
patch design) should not proceed to writing an actual hook/dispatcher
until this gap is closed — either by finding a genuinely free region (a
wider systematic scan, tested per-overlay) or by choosing a different
strategy this document didn't need to invent (e.g. the development-only
external patching approach in 13.5, scoped down to "verified safe for
this run only," rather than a permanent cave).
