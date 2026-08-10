# Mode 3 (`Y_COLLECTION_MODE`) Trigger Investigation

Traces the exact script-decoder branch responsible for producing the
per-frame mode value `3` (`Y_COLLECTION_MODE`, see `FRAME_RENDER_MODES.md`),
and documents an attempted (inconclusive) live/synthetic trigger.

## Static decoder findings (CONFIRMED via live disassembly)

The mode-selection flags byte (`sp+0x22` in `FUN_800481b0`'s frame,
offset `+0x0A` of the output struct `FUN_80049168` — the script-
bytecode decoder — writes to) is reset to 0 at the top of every decoder
call (`sb $zero,0xa($s4)` at `0x8004920c`), then set by whichever
control-code branch executes.

**Exact producer chain for flags value `0x42` (bit `0x40` + bit `0x02`,
the `Y_COLLECTION_MODE` condition):**

```
FUN_80049168 (script decoder), entry 0x80049168
  lh   $a1, 8($s4)                    ; 0x80049240 -- read raw script word
  andi $v1, $a1, 0xc000                ; 0x80049264 -- top 2 bits = family
  bne  $v1, 0x8000, [family B/other]     ; 0x80049270 -- must be family "10" (CONTROL_A)
  andi $v1, $s3, 0x3f00                    ; 0x80049274 -- subtype = bits 8-13
  ...
  beq  $v1, 0x500, 0x80049448                ; 0x800492e4 -- subtype == 0x0500
  andi $v0, $s3, 0xff        [delay slot]      ; 0x800492e8 -- v0 = parameter byte

0x80049448: bnez $v0, 0x8004945c            ; if parameter != 0:
0x8004944c: ori  $s5, $zero, 2    [delay slot, ALWAYS executes regardless of branch]

  [parameter == 0 path, 0x80049450]:
    flags |= 2                                 ; WIDTH_MODE-shaped, not our target

  [parameter != 0 path, 0x8004945c -- OUR TARGET]:
0x8004945c: lbu $v0, 0xa($s4)
0x80049464: ori $v0, $v0, 0x42              ; flags |= 0x42  <-- Y_COLLECTION_MODE bits
0x80049468: sb  $v0, 0xa($s4)
0x8004946c-80: also sets DAT_800a4cf8=0xf0, DAT_800a4ce4=0xfffe
0x80049484: j 0x80049ca0                     ; common exit
```

**Cross-reference**: subtype `0x0500` is already documented in this
project's OWN `gcrts/control_position_risk.py` as `pause_flag_a`, part
of `STALE_POSITION_MEANINGS` — confirmed here (independently, via raw
MIPS disassembly, not by reusing the existing name) to also be the
producer of `Y_COLLECTION_MODE` when its parameter byte is nonzero.
This is a genuinely new finding: `pause_flag_a`'s significance was
previously understood only as "sets `DAT_800a4d11=1`, causing a stale-
position character misplacement" — its role in triggering the frame-
level Y-collection mode had not been connected before this
investigation.

**Loop-back check (why the decoder should exit, not loop past this
word)**: `0x80049ca0` (common exit) increments a call counter, then
checks `andi $v0,$s5,0xff; beqz $v0,0x80049214` (loop back to process
another word only if `s5==0`). For our target branch, `s5` is set to
`2` unconditionally in the delay slot at `0x8004944c` — so the decoder
should NOT loop past our injected word; it should return immediately
after setting `flags=0x42`, making it the last (and only) mode value
for that frame's decoder call.

## Formal matcher

```python
def produces_y_collection_mode(word: int) -> bool:
    FAMILY_MASK = 0xC000
    FAMILY_A = 0x8000
    SUBTYPE_MASK = 0x3F00
    SUBTYPE_PAUSE_FLAG_A = 0x0500
    return (
        (word & FAMILY_MASK) == FAMILY_A
        and (word & SUBTYPE_MASK) == SUBTYPE_PAUSE_FLAG_A
        and (word & 0xFF) != 0  # nonzero parameter
    )
```

No additional decoder state is required for THIS specific branch beyond
the raw word value itself — the branch is reached purely from the
family/subtype/parameter bits, with no precondition on other globals
checked in the disassembly.

## Script-data search findings

- **Live script buffer (current scene at time of search)**: scanned
  2048 words, 0 matches.
- **Multiple different live scenes** (2 additional scene changes,
  scanned identically): 0 matches each.
- **Offline K0LINK.CDB (chapter 0's script resource, read directly from
  the disc image via `gcrts.iso9660` + `gcrts.cdb_codec`)**: attempted
  to parse the documented directory-table format (2048-byte table,
  512 4-byte entries) and decompress individual entries to search their
  content. **Only the first entry decompressed successfully**; entries
  2+ failed with index-out-of-range errors, and a search for a second
  directory table at plausible 2048-byte-aligned boundaries found no
  valid chain. This is consistent with this project's own pre-existing,
  documented uncertainty about K0LINK.CDB's exact indexing scheme
  (`README.md`: "the exact indexing scheme that selects which
  compressed chunk corresponds to a given character code or dialogue
  line" is explicitly listed as "Not implemented yet"). Not pursued
  further — attempting to reverse-engineer this format from scratch
  risked an unbounded detour into unconfirmed territory the task
  explicitly cautions against guessing at.

## Synthetic test findings

Built a minimal test buffer (`"Test"` + raw word `0x8501`
[`pause_flag_a`, subtype `0x0500`, parameter `1`] + `"Done"` +
`0xFFFF` terminator) using `gcrts.script_encoder.tokenize_translated_text`
for the safe text and the guarded `write_script_buffer` for the write
(the higher-level, editor-facing `live_injection` path was intentionally
NOT used, since it drops `pause_flag_a`/`pause_flag_b` codes outright
for any edited unit — using the low-level write directly was necessary
and is consistent with the task's permission to "use the proven
full-buffer encoding and guarded injection path").

Backed up the original buffer before each write; restored it after
each attempt; verified every write and restore via readback. Two
attempts:

1. First attempt: injected while a cutscene (no active textbox) was on
   screen — the buffer sat unread while the game was in a dialogue-free
   moment. Restored without effect observed either way (inconclusive by
   construction, not a negative result).
2. Second attempt: injected while the emulator was paused with
   narration text visibly active on screen (confirmed via screenshot),
   specifically to ensure the read cursor would reach the injected
   content promptly. The user unpaused and advanced through
   substantial dialogue (71 mode-aware capture hits, spanning multiple
   distinct script buffer states). **`Y_COLLECTION_MODE` did not appear
   in any of the 71 captures.**

## Confirmed facts vs. unresolved assumptions

**Confirmed**: the exact decoder branch, instruction addresses, and bit
pattern producing `flags=0x42` (`Y_COLLECTION_MODE`). The branch logic
and loop-back condition were re-verified against the raw disassembly
after the synthetic test's null result, specifically to rule out "my
understanding of the trigger is wrong" before accepting a weaker
conclusion — the logic holds up.

**Unresolved**: whether the synthetic injection actually reached the
decoder at all. The most likely explanation is a script-cursor timing
mismatch — the game's read position may have already been past, or
never reached, the small 20-byte injected region during the observed
capture window, especially since the exact mechanism connecting the
live script buffer's base address to the decoder's own read cursor
(`s4+8` in `FUN_80049168`'s frame) was not independently traced this
round. This is a "missing verification of a prerequisite," per the
task's own Step 8 framing — NOT evidence the opcode is wrong.

## Follow-up round: precise cursor-targeted injection (still inconclusive, for a NEW reason)

A later round found the exact decoder read-cursor formula (see
`DECODER_READ_CURSOR.md`): `read_address = 0x801FE800 + DAT_800a4cea *
2`, confirmed live by reading the cursor, computing the address, and
finding real, plausible script data there (small character-code-shaped
values and a genuine `0xFFFF` terminator in the surrounding window).
This directly explains why the EARLIER synthetic injections (writing
to the buffer's absolute start, byte 0) never worked: the cursor was
almost certainly already well past offset 0 by the time each injection
happened.

A corrected, cursor-targeted injection was attempted: read the cursor,
compute the exact next-read address, back up the original word, write
`0x8501` there, verify via read-back, then have the operator advance.
**Result: inconclusive again, but for a genuinely new and important
reason** — see `DECODER_READ_CURSOR.md`'s "Major follow-up finding"
section. The cursor DID advance past the injection point (55 → 93,
confirming the decoder reads through this region), but the word at the
injection address had reverted to `0x0000` by the time it was
re-checked — indistinguishable from the pre-injection original (also
`0x0000`), meaning consumption cannot be confirmed either way from this
alone. The leading explanation: the live script buffer is dynamically
refreshed/streamed as the game progresses, not filled once per scene —
the injected word may have been overwritten by this natural refresh
before the cursor actually reached it, a narrower and more fragile
timing window than assumed.

**Correction**: the operator confirmed a quickload happened between the
injection and the follow-up check — fully explaining the reverted word
and jumped cursor value via the SAME already-established "quickload
silently reverts external memory writes" behavior documented repeatedly
earlier this session, not a new "dynamically streamed buffer" property.
See `DECODER_READ_CURSOR.md`'s correction note. Re-attempt needed with
explicit confirmation that no quickload occurs between injection and
check.

Separately, still true regardless of the above: the two candidate
secondary-effect globals checked (`DAT_800a4cf8`, `DAT_800a4ce4`) both
turned out to be unreliable verification signals (the former changes
naturally per-character for unrelated reasons; the latter was already
in its "fired" state before this test began), so a future attempt needs
a cleaner, unambiguous verification signal — ideally a live breakpoint
positioned to fire only once, immediately after the exact load
instruction consumes whatever word is actually present at that moment
(not assumed from a static disassembly location, which this session
found to be unreliable to break at directly — see the "decoder entry
vs. actual read instruction" confusion resolved via the `$a2`/`ra`
filtering technique in this round's tooling).

## FINAL CONFIRMATION: trigger proven live, unambiguously

A clean, low-latency two-stage breakpoint capture (full detail in
`DECODER_READ_CURSOR.md`'s "FINAL CONFIRMATION" section) closed this
out completely:

1. Cursor-targeted injection of `0x8501` at the fresh, freshly-re-read
   cursor address (`0x801FE86E`, cursor=55).
2. Breakpoint at the exact consumption instruction (`0x80049240`) fired
   on hit 1, confirming `0x8501` sat exactly at the address about to be
   read (`s4+8`), with negligible elapsed time (no drift, no quickload
   in between this time).
3. A second breakpoint a few instructions past the flags write
   (`0x80049470`) fired on hit 1 (same `$s4`), confirming the flags byte
   read back as **`0x42`** — i.e. the decoder actually took the
   `pause_flag_a` nonzero-parameter branch and produced
   `Y_COLLECTION_MODE`'s flag value as a direct, live consequence of the
   injected word.
4. Original word restored and verified; both breakpoints removed;
   execution resumed cleanly.

This is a complete, causal, live-verified chain from a specific script
control word to the exact per-frame mode flag it produces — not a
static disassembly argument, not a plausible-value coincidence, and not
a synthetic test with an ambiguous or quickload-confounded result.

## What this does NOT claim

Per the task's explicit "Not Success" list: this document does not
claim the mode-3 branch exists in disassembly is sufficient (it isn't —
static existence was already known before this round); does not treat
an opcode's numerical/semantic match to `pause_flag_a` as proof by
itself (the full branch trace, delay-slot behavior, and loop-back
condition were independently re-verified); and does not claim the
synthetic injection reached the decoder branch on its own weight alone
— see the "FINAL CONFIRMATION" section above, which closes this with a
live breakpoint chain, not an assumption.
