# Dialogue GPU Packet Map

Field-level map of what's been confirmed, live-disassembled, and (where
noted) live-tested in the per-character render call chain. Read
alongside `TEXT_POSITION_SOURCE_PLAN.md` (narrative) and
`TEXT_POSITION_TRACE_LOG.md` (row-by-row captures).

## Position-record layout (14 bytes, base `0x800a3dd0`, index = `DAT_800a4cd8`)

| offset | raw value (sample) | interpretation | source instruction | live modification result | confidence |
|---|---|---|---|---|---|
| `+0` | 0, 16, 32... (cdc×16) | fixed-stride cache/atlas X-like field (`>>2` applied by reader) | `FUN_8004a8c0` @ `0x8004a994` | produces a real, visible but non-qualifying artifact (stray disconnected dot); does NOT move the live dialogue text | HIGH (artifact), see caveat below re: buffer timing |
| `+2` | 0 (constant, low counter range) | same family as `+0`, row/quotient half of the same divmod formula | `FUN_8004a8c0` @ `0x8004a9d0` | not independently tested | MEDIUM |
| `+4` | `FUN_8004aa08`'s own return value | status/width return from the glyph-upload call | `FUN_8004a8c0` @ `0x8004a9f0` | not tested | LOW |
| `+6` | not captured | read by `FUN_8004aae8` (`lhu a1,6(a1)`, record[0] specifically, unindexed) as an argument to `FUN_8007ad74` | consumer: `FUN_8004aae8` @ `0x8004aafc` | not tested | LOW |
| `+8` | 10, 26, 38... (real proportional widths) | wrap function's logical cursor X | `FUN_8004a370` @ `0x8004a50c` (normal case), `0x8004a5bc` (wrap-reset case) | **no visible change** when modified | HIGH |
| `+0xA` | 152 (constant within a line) | wrap function's logical cursor Y | `FUN_8004a370` @ `0x8004a5ec` | not independently modified (only `+8` was tested) | MEDIUM |
| `+0xC` | `DAT_800a4cec` (byte) or `0xffff` sentinel | validity/reveal-state flag, gated by `DAT_80094d24` | `FUN_8004ab1c` @ `0x8004ab80` | not tested | MEDIUM (disassembly-only) |

## GPU-adjacent helper functions (confirmed via live disassembly + one resolved string)

| function | role | evidence |
|---|---|---|
| `FUN_8004aa08` (`0x8004aa08`) | decompresses current glyph (`FUN_8007681c`) and calls a GPU-upload primitive (`0x800786b8`) with a destination rect built from record `+0`/`+2` | live-captured rects: X=320+ (fixed +4/character), Y=256, W=4, H=16 — see `TEXT_POSITION_TRACE_LOG.md` event set C |
| `FUN_8004aae8` (`0x8004aae8`) | reads record[0]'s `+4`/`+6` (unindexed — always record 0, not current index), calls `FUN_8007ad74` | disassembled fully this round |
| `FUN_8004ab1c` (`0x8004ab1c`, a SEPARATE function immediately after, not a branch of the above) | writes record `+0xC` — a validity/state flag gated by `DAT_80094d24` (itself managed by a small getter/setter cluster: `DAT_80094d24`, `DAT_80094d26`, `DAT_80094d27`, `DAT_80094d28`) | fully disassembled; not live-tested |
| `FUN_8007ad74` (`0x8007ad74`–`0x8007ad88`) | pure bit-packing helper: `(a1<<6) \| ((a0>>4)&0x3f)` — packs two small values into one word, returns it, no side effects | fully disassembled |
| `FUN_8007ad8c` (`0x8007ad8c`–`0x8007ae24`, the function CONTAINING the actual indirect call — previously mis-attributed to `FUN_8007ad74`) | checks debug-mode flag (`jal 0x800783ac`); if active, packs tpage/clut-shaped bitfields and calls a **debug printf** through an indirect BIOS-call trampoline; if inactive, packs a different bit layout and calls the SAME trampoline (with a different packed value — meaning the printf is called either way, just with different formatting/verbosity) | indirect target resolved live (see below); target's string CONFIRMS this is debug logging |
| `FUN_8007acdc` (`0x8007acdc`) | same debug-check + pack-and-return pattern as `FUN_8007ad74`, operating on `(a0,a1,a2,a3)`; receives `(0, 0, param_2[0]=base_X, param_2[2]=base_Y)` from `FUN_8004aa08`; packs into what the resolved debug string's format (`"clip (%3d,%3d)-(...)"`) implies is a **clip-rectangle attribute word**, not a screen destination | fully disassembled; return value's consumption not traced further |

## Resolved indirect-call target

The function pointer read from `0x8009d448` resolves (live-confirmed,
not assumed) to `0x80077f68` — a tiny trampoline:
```
addiu $t2, $zero, 0xa0
jr    $t2
addiu $t1, $zero, 0x3f     ; delay slot
```
This is the **standard PS1 BIOS A0-table call convention** (function
number in `$t1`, jump to the BIOS dispatch vector at `0xa0`). The first
argument passed at the call site is a **fixed, hardcoded address**
(`0x80046e90`), read live and confirmed to contain the literal string:

```
tpage: (%d,%d,%d,%d)
   clut: (%d,%d)
  clip (%3d,%3d)-(...)
```

**This conclusively identifies the call as a debug-mode printf logging
GPU primitive attributes (tpage/clut/clip) — not a primitive submission
or ordering-table insertion.** This is a resolved fact (live-read
string content), not an inference from bit-packing shape alone — the
kind of claim the task explicitly warns against making without this
level of confirmation.

## Open question this map does NOT resolve

The debug-print chain establishes that tpage/clut/clip fields exist and
get logged, but does not itself prove where the primitive's plain
destination X/Y (if stored separately, unpacked, as most PS1 GPU sprite
primitives do) lives, or that the `FUN_8004aa08` upload rect (X=320+,
Y=256) is actually invisible. See `INDIRECT_RENDER_TARGETS.md` for the
specific double-buffering alternative this surfaced, which is NOT yet
ruled out.
