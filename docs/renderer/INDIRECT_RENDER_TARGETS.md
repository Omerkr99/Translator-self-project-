# Indirect Render Targets

Resolution of the indirect-call target found inside the per-character
render chain, and the credible alternative hypothesis it surfaced.

## The resolved target

Function pointer at `0x8009d448` (live-read, not assumed): `0x80077f68`.

Disassembly of `0x80077f68`:
```
0x80077f68: addiu $t2, $zero, 0xa0
0x80077f6c: jr    $t2
0x80077f70: addiu $t1, $zero, 0x3f    ; delay slot
```

This is the canonical PS1 BIOS A0-table call sequence: function number
in `$t1`, jump to the BIOS dispatch vector `0xa0`. Adjacent addresses
(`0x80077f78`, `0x80077f88`, `0x80077f98`, `0x80077fa8`, `0x80077fb8`)
are five MORE trampolines of the same shape calling different A0/B0
function numbers (`0x1b`, `0x17`, `0x19`, `0x2f`, `0x38` respectively) —
these are a cluster of small stub functions in the same code region,
not branches of one function. Only `0x80077f68` (A0 function `0x3f`) is
the one actually stored at `0x8009d448` and reached from this call
chain.

**Executable/overlay**: same session profile as the rest of this
investigation (`UNIDENTIFIED_SESSION_2026-07-27` in
`mips_patch_profiles.json` — shifted layout). Not independently
fingerprinted against a named `CAP*.EXE`.

**Resolved via**: a plain live memory read of the function-pointer slot
(no breakpoint needed — it's data, not code), then a live disassembly
read of the target address. Both steps reproducible with the standard
`GdbClient`/`capstone` pattern already established.

## What it actually does (proven, not inferred from the call shape alone)

The call site (`0x8007ad8c`–`0x8007ae24`, previously mis-attributed as
part of `FUN_8007ad74` before this session corrected the function
boundary) passes a **fixed, hardcoded address** (`0x80046e90`) as the
first argument. Reading that address live returns the literal string:

```
tpage: (%d,%d,%d,%d)
   clut: (%d,%d)
  clip (%3d,%3d)-(...)
```

A0 function `0x3f` combined with a format-string-shaped first argument
and packed integer arguments matches the standard PS1 BIOS `printf`
calling convention. **This is confirmed by live-reading actual string
content, not inferred from the bit-packing shape or the BIOS call
number alone** — satisfying the task's own bar against claiming success
from "GPU-looking bit packing" or "static decompiler output" in
isolation.

The call is gated by a debug-mode check (`jal 0x800783ac; beqz
$v0,...`) — meaning this printf only fires when some debug/verbose flag
is active. Both the "debug active" and "debug inactive" branches
(`0x8007ad8c` region vs `0x8007addc` region) ultimately call the SAME
trampoline (`0x80077f68`) with differently-packed arguments — meaning
even the "inactive" branch appears to still print, just with a
different bit layout. This wasn't fully explained and is flagged as an
open detail, not resolved.

**Conclusion**: this indirect-call target is a debug logging path,
not a primitive-submission or ordering-table-insertion mechanism. The
"GPU primitive construction" framing from the prior task's hypothesis
does not hold for THIS specific call — it explains why tpage/clut/clip
values exist and get READ here (for logging), not where they get
WRITTEN or submitted for actual drawing.

## Credible alternative hypothesis surfaced, NOT yet ruled out

Everything upstream of this debug-print call remains genuinely
GPU-attribute-shaped (tpage/clut/clip packing in `FUN_8007acdc`, the
sibling of the debug-print's own packer). Per the task's own required
rigor, this session's earlier conclusion — "`FUN_8004aa08`'s upload
destination (X=320+, Y=256) is off-screen, therefore a texture cache,
therefore not the visible draw" — rested on an assumption that was not
independently verified: that X=320 is necessarily invisible.

**PS1 VRAM is 1024 pixels wide.** A common convention for
double-buffered rendering is a front buffer at X=0-319 and a back
buffer at X=320-639 (or similar), with the GPU's own display-area
setting controlling which is currently visible; the buffers swap roles
every frame. If this game uses that convention, X=320 could be the
CURRENT BACK BUFFER, not a texture cache — meaning a write there is a
real, correctly-processed frame that simply hadn't been swapped to
visible yet at the moment a screenshot was taken.

This would mean the earlier live-modification test (`+0` change → only
a stray-dot artifact, no visible main-text movement) may have been
inconclusive due to **buffer-swap timing**, not because the field is
provably unrelated to the final screen position. The task's own
distinction — "produces an artifact" does not equal "confirmed as
screen position" — cuts both ways here: the ORIGINAL "ruled out"
conclusion also isn't fully proven under this alternative.

## Double-buffering hypothesis — tested this session, NOT supported

Repeated the `+0` live-modification test (break at `FUN_8004aa08`'s
entry, change `+0` from 48 to 800, resume), then captured **5
screenshots in quick succession** (~180ms apart, ~800ms total window)
instead of a single shot, specifically to catch a delayed appearance if
a buffer swap were the explanation.

**Result: no delayed appearance across any of the 5 frames.** The
dialogue text ("ミカ：窓の外・・・、なんか動いた・・・") rendered
identically and correctly across the first four captures, then cleared
naturally (textbox emptying as part of normal game advancement, not a
glitch) by the fifth. At no point did a shifted or displaced glyph
appear at a sensible on-screen position.

**This does not support double buffering as the explanation.** The
original conclusion — `FUN_8004aa08`'s upload destination is a
texture/glyph cache, not the visible screen buffer — now stands having
been actively tested against the most credible alternative, rather than
merely assumed. This closes the double-buffering question for this
field; it should not be re-opened without new evidence per the
project's standing rule on re-testing ruled-out candidates.

## Remaining next experiment

This doesn't by itself find the real screen X/Y source — per
`EXPERIMENT_PLAN.md`'s Step D, since this whole `FUN_8004aa08` chain
(upload + debug-print + clip-pack helpers) is now confirmed
cache/logging/attribute-only, the search should broaden to: other
callers of `0x800786b8` (the GPU-upload primitive) or of the ACTUAL
ordering-table-submission mechanism (not yet located — everything found
so far either logs or packs attributes, nothing yet clearly "submits a
primitive for the GPU to draw this frame"). A live scan (the same
whole-code-segment JAL-search technique already used successfully this
session to find `FUN_8004a8c0`'s and `FUN_8004aae8`'s callers) for
other callers of `0x800786b8` is the most direct next step.

### Update (later session): `0x800786b8` itself confirmed stale, chain continued

A later round found `0x800786b8` no longer valid for the currently-
loaded profile (the code layout had drifted to this session's own
independently-mapped chapter-1 overlay). Re-deriving forward from that
profile's confirmed render-loop dispatch found this profile's own
equivalent chain, including a nested cache-preparation function
(`0x8003B144`) whose upload rect (`X=328,Y=320,W=4,H=16`) matches this
exact document's own `FUN_8004aa08` destination shape almost exactly —
independent cross-validation, in a second overlay, of the
"off-screen texture cache, not the visible framebuffer" conclusion.
Full detail, the complete mode-dispatch map, and the one remaining
inconclusive lead (candidate D, `0x8003AAAC`) are in
`MASTER_RENDER_MODE_MAP.md` and `VISIBLE_DIALOGUE_COMPOSITION_PATH.md`.
