# Decoder Read Cursor — CONFIRMED

## FINAL CONFIRMATION (live breakpoint, unambiguous, no quickload confound)

A clean retry, done immediately after fresh dialogue was reloaded (cursor
re-read as 55, matching the very first attempt's starting position — no
assumption of continuity was made; the cursor was re-verified fresh
immediately before injecting, per the operator's explicit instruction
that any quickload invalidates in-flight injection state):

1. Read cursor = 55, computed `inject_addr = 0x801FE86E`, backed up the
   original word (`0x0000`), injected `0x8501`, verified via read-back.
2. Armed a breakpoint at `0x80049240` (the exact `lh $a1,8($s4)`
   consumption instruction) and continued. **It fired on hit 1** —
   filtered by the saved `$a2` at `sp+0x38 == 0x800A4BD0` (the known
   `FUN_800481b0` caller). Read `s4+8` directly (the exact address the
   `lh` was about to load from): **`0x8501`** — our injected value,
   confirmed sitting exactly where the decoder was about to read from,
   with essentially zero elapsed time between injection and this check.
3. Removed that breakpoint, armed a second breakpoint at `0x80049470`
   (a few instructions past the `sb $v0,0xa($s4)` flags write at
   `0x80049468`, still inside the same decoder call) and continued.
   **It fired on hit 1**, filtered by matching `$s4` to the same value
   seen in step 2. Read the flags byte at `s4+0xA` directly: **`0x42`**
   — confirming the decoder actually took the `pause_flag_a`
   nonzero-parameter branch and wrote `Y_COLLECTION_MODE`'s flag value,
   live, as a direct causal consequence of the injected word.
4. Restored the original word (`0x0000`), removed both breakpoints,
   verified restoration via read-back (`True`), continued execution.

This closes the previously-open gap (both the "does the injected word
reach the load register" question and the "does the branch actually
fire" question) with a single clean, low-latency, two-stage
breakpoint capture — no single-stepping was needed for this version
(see the note below on why single-stepping directly at a software
breakpoint's own address is unreliable on this stub).

**A related tooling note, discovered along the way**: single-stepping
(`s`) immediately at the address of an already-armed software breakpoint
can re-trigger the trap instruction itself rather than executing the
real instruction underneath it, producing garbage register values
(observed once: `$a1` read back as `0xFCF2` instead of the expected
`0x8501` after stepping over `0x80049240` while its breakpoint was still
armed). The fix used in the final, successful version: remove the
breakpoint (`z0`) *before* single-stepping or before relying on further
normal execution past that address, rather than stepping directly
through a still-armed trap.



## Exact formula (LIVE-VERIFIED)

```
script_base   = 0x801FE800           (fixed, already known -- gcrts.live_extract.SCRIPT_BUF_ADDR)
cursor_addr   = 0x800A4CEA           (global, 16-bit, word-index units)
cursor_scale  = 2                     (bytes per word)

read_address  = script_base + (*cursor_addr) * cursor_scale
```

## How this was found

Full trace of `FUN_80049168` (script decoder) from entry (`0x80049168`)
to the actual word-consumption instruction (`0x80049240: lh $a1,
8($s4)`):

```
0x80049210: lui  $s2, 0x801f
0x80049214: ori  $s2, $s2, 0xe800      ; s2 = 0x801FE800 (script buffer base)
0x80049218: addiu $s1, $s4, 8           ; s1 = s4+8 (decoder's own input field)
0x8004921c: move $a1, $s1                 ; a1 = destination for the copy below
0x80049220: lui  $s0, 0x800a
0x80049224: addiu $s0, $s0, 0x4cea          ; s0 = &DAT_800a4cea (the cursor)
0x80049228: lhu  $a0, ($s0)                   ; a0 = cursor value
0x8004922c: ori  $a2, $zero, 2                  ; a2 = 2 (byte count)
0x80049230: sll  $a0, $a0, 1                      ; a0 = cursor * 2
0x80049234: jal  0x80077f48                         ; memory-copy utility
0x80049238: addu $a0, $a0, $s2                        ; a0 = script_base + cursor*2 (source addr)
0x8004923c: move $s5, $zero
0x80049240: lh   $a1, 8($s4)                              ; NOW read the copied word
```

`0x80077f48` is called as `copy(dest=s4+8, source=script_base+cursor*2,
count=2)` — a 2-byte memory copy fetching exactly one script word from
the live buffer into the decoder's own input field, which is read
immediately afterward at `0x80049240`.

## Live verification

```
DAT_800a4cea (cursor)     = 42
computed read address      = 0x801FE800 + 42*2 = 0x801FE854
word at that address        = 0x0015
```

Context window around that address (`0x801FE84C`-`0x801FE86C`):
`bb00 0086 008a ffff 1500 1900 5201 1900 0e00 0200 ac00 2600 0086 008a ffff 1500`
— small positive values consistent with direct character codes, with a
genuine `0xFFFF` terminator visible, exactly matching expected script
structure. This is real confirmation via live read-back, not an assumed
format.

## Why this explains the earlier synthetic-injection failures

Both prior synthetic injection attempts (`MODE3_TRIGGER_INVESTIGATION.md`)
wrote to `script_base + 0` (byte 0 of the buffer) — the buffer's
absolute start, not the actual read cursor. Since the cursor had almost
certainly already advanced well past offset 0 by the time each
injection was written (as this round's live read confirms, showing a
cursor position of 42 during ordinary play), the game's decoder was
never reading from the location that got overwritten. This was a
genuine methodology gap, not a wrong trigger opcode — now closed.

## Not yet independently confirmed

- Whether the cursor ever wraps, resets, or is reinitialized at unit/
  scene boundaries (not observed this round).
- Whether `0x80077f48` performs anything beyond a plain 2-byte copy
  (not fully disassembled this round — inferred from its call
  signature and the surrounding code's behavior, consistent with the
  `bcopy`-style calls seen elsewhere in this codebase).

## Correction: the "rolling buffer" theory below was based on an incomplete premise

The operator confirmed after the fact that a **quickload** happened
between the injection and the follow-up check — the same
"quickload silently reverts any external memory write" behavior
already established multiple times earlier this session (see
`MIPS_PATCH_PLAN.md`'s Phase 7 correction and the overlay-variance
findings). That fully explains both the reverted word AND the jumped
cursor value, without needing a new "dynamically streamed buffer"
theory at all — a save-state load resets the ENTIRE memory image,
including both the injected word and the cursor's own position, to
whatever that save captured. The section below is kept for the record
(the mechanics described are real observations), but its interpretation
is superseded by this simpler, already-known explanation. Re-attempt
needed with explicit confirmation that no quickload occurs between
injection and check.

## Original write-up (superseded interpretation, see correction above)

A precise, cursor-targeted injection test (writing `0x8501` at the
EXACT computed next-read address, not the buffer's absolute start —
correcting the earlier methodology gap) produced a genuinely new,
important result:

1. Confirmed cursor = 55, computed address `0x801FE86E`, original word
   there = `0x0000`. Backed up, injected `0x8501`, verified via
   read-back.
2. User advanced dialogue (multiple lines, confirmed via screenshots
   showing real narration text progressing normally, with one visually
   noted anomaly — a slightly left-shifted first character on one
   line, not conclusively tied to this test either way).
3. Re-read after advancing: **cursor had moved to 93** (confirming the
   decoder genuinely read through and past word-index 55, not stuck or
   skipping). **But the word at the injection address had reverted to
   `0x0000`** — neither the injected `0x8501` nor the pre-injection
   original (which was also, coincidentally, `0x0000`) in a way that
   proves consumption either way, since both are indistinguishable.
   Secondary globals (`DAT_800a4cf8`, `DAT_800a4ce4`) were checked but
   turned out to be unreliable indicators: `DAT_800a4cf8` changes
   naturally per-character regardless of any pause-flag branch (its
   value drifted from `0xbb` to `0xd5`, neither matching the
   `pause_flag` branch's own `0xf0` write), and `DAT_800a4ce4` was
   ALREADY at the "fired" value (`0xfffe`) before this test even began
   — meaning it could not distinguish a fresh trigger from stale state.

**Interpretation**: the live script buffer at `0x801FE800` is not a
single static block filled once when a scene loads — it appears to be
refreshed/rewritten as the game streams new content in, likely in
chunks smaller than a whole scene. This means a synthetic injection
must land in a window between "content is written here" and "cursor
reads this exact word," which may be considerably narrower than one
full dialogue advance — writing once and waiting for an arbitrary
"advance" is not sufficient, since the buffer can be refreshed out from
under the injected value before the cursor arrives.

**This is the same class of finding as `MIPS_PATCH_PLAN.md`'s
"Phase 7 correction"**: a plausible-looking test that doesn't actually
prove consumption. Recorded honestly rather than claimed as a trigger
success. See `MODE3_TRIGGER_INVESTIGATION.md` for the full write-up and
the precise next experiment this implies.
