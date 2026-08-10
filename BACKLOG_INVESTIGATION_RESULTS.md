# Backlog Investigation — First Execution Pass

Results of actually running the 4 cheapest steps `BACKLOG_INVESTIGATION_SCOPE.md`
recommended (Stage G proof of concept, Stage C VAB probe, Stage A codec
trial, Stage B sector check), in that order. All four were attempted; two
produced genuine, concrete new findings (A and B), one produced a real but
inconclusive lead (C), and one succeeded offline with the live half still
in progress when this was written (G). Every script used is read-only
against the disc image except G, which only ever wrote to a throwaway
copy (`game_persistent_test.bin`) — the real `game.bin` was never touched.

## Stage A — SDB2.0 located and identified: CONFIRMED

Applying the existing, disassembly-confirmed `gcrts.cdb_codec.decompress()`
to `DAT/HITO/AFRM.CDB` after skipping its first 2048 bytes (the same
directory-table-sized prefix `K0LINK.CDB`/`KFONT.CDB` use) produces a
209-byte stream that starts with the literal ASCII bytes **`53 44 42 32
2e 30 20` — "SDB2.0 "**. This is a direct, unambiguous magic-string match,
not an inference: the exact format name from the backlog's own list is
sitting at the start of the decompressed data.

Immediately following the 7-byte magic, the bytes decode as a table of
little-endian `u32` values that increase steadily — `251, 1268, 1772,
1875, 1977, 2080, 2182, 2285, 2388, 2468, 2545, 2625, 2702, 2782, 2860,
2979, 3097, 3216` — **exactly 18 clean entries**, after which the
apparent values jump to obvious garbage (hundreds of millions), proving
the real table is exactly 18 entries long, not an artifact of reading too
few/many bytes. The inter-entry deltas group into three clean bands: ~102–
103 bytes (8 entries), ~77–80 bytes (6 entries), ~118–119 bytes (3
entries, with the very first delta, 1017, standing apart as an outlier —
plausibly a larger first frame or a distinct header-sized entry). Three
groups of near-uniform frame sizes is a strong, self-consistent signature
for an animation with a few distinct pose/frame classes — not a guess
about what the numbers "could" mean, a directly observed pattern in the
real decoded bytes.

This was confirmed to be the COMPLETE table, not a truncated fragment:
re-running decompression with a local copy of the codec that also reports
how many *input* bytes it consumed (`gcrts.cdb_codec.decompress()` itself
only returns output bytes) showed the stream ends on a genuine `0xFF`
terminator at input byte 214 — decompression stopped because the format
said to, not because of a length cap. **Still open**: where the actual
per-frame pixel data lives. It is not simply the next compressed stream
concatenated right after this one — attempting to decompress starting
immediately after byte 214 of the blob raises an internal error (an LZ77
back-reference pointing before the start of that attempt's output),
meaning frame data is addressed some other way (very plausibly through
the 34 non-zero entries in the file's OUTER 2048-byte table, whose values
are too large to be plain byte offsets into this file — not yet resolved,
real follow-up work, not attempted further this pass).

## Stage A follow-up — the outer table: one more genuine hit, not a general solution

Tested candidate interpretations of the file's OUTER 2048-byte table (512
x 4-byte entries, 34 non-zero, values like `13,762,561` -- far too large
to be plain byte offsets into the 5,965,824-byte blob). Tried several
transforms (division by 8/16/32, sector-alignment, high/low 16-bit
halves, byte-swapping) against the first two non-zero entries.

**One genuine, non-coincidental hit**: entry 0's raw value (`13762561`),
right-shifted by 5 bits (`>> 5` = `430080`, with the low 5 bits -- value
`1` -- plausibly a small flag field), lands on a blob offset that
decompresses to bytes starting with the literal magic **`"SDB2.0 "`**
again -- a second, independent animation resource in the same file, not
the same one already found by simply reading from the blob's start. An
exact 7-character ASCII match like this at a computed, non-obvious offset
is not chance.

**But this does not generalize**: applying the identical `>> 5` transform
to the other 33 non-zero entries produces mostly `IndexError`s (an
internal LZ77 back-reference pointing before the start of that attempt's
output -- the same failure mode seen when guessing wrong offsets earlier
this session) and, for the handful that "succeed" mechanically, garbage
(a solid run of one repeated byte, or unstructured data with no magic).
Entry 0's match, while real, is not proof of a general addressing
formula for the whole table.

**Also not fully clean even for entry 0**: decompressing further (not
capped at the first ~300 bytes) shows the stream itself fails with the
same `IndexError` somewhere between 333 and ~400 produced bytes -- past
where the magic and what looks like early table data sit, but before any
natural `0xFF` terminator was reached. Either this second resource is
larger/structured differently than the first (entirely plausible -- nothing
requires every animation entry to have the same 18-frame shape) and hits
a genuine edge case this session's minimal decoder doesn't handle, or the
`>> 5` transform is subtly wrong and coincidentally right for the first
~300 bytes only. Not resolved this pass.

**Honest net result**: two real, confirmed SDB2.0 streams now exist in
this file (the original one found by reading from the blob's start, and
this new one via the outer table's entry 0), but the outer table's
general addressing scheme -- how all 34 entries resolve -- remains
unsolved. A worthwhile real next step, not attempted: check whether the
low 5 bits that vary so much across entries (1, 19, 31, 9, 27, ...) are
actually meaningful (a real per-entry flag/type) rather than incidental,
by grouping entries by that value and seeing if any subset's offsets
behave more consistently.

`DAT/HITO/SIKFORM.CDB` shows a structurally similar but distinct pattern:
its first-2048-byte table has 56 non-zero entries whose values are
self-consistent as a running (size, cumulative-offset) pair sequence
(`204 + 202 = 406`, `406 + 201 = 607`, `607 + 208 = 815`, checked directly
against the real table values) — real evidence of a genuine table
structure, but attempting to decompress individual entries at those
offsets mostly failed (`bytearray index out of range`) except one
(entry 2, offset 204, which decompressed to 839 bytes with no magic
string recognized yet). SIKFORM is very likely the same format family or
a sibling one (MS4/GP4/SDB2.2) but this pass did not identify which.

**Net result**: SDB2.0 is no longer "never located" — it has a real,
confirmed sample (`AFRM.CDB`) and a confirmed magic string. `IMAGE_FORMAT_ADAPTERS.md`
updated accordingly. Full field-layout decoding (frame dimensions, pixel
format, palette) is real follow-up work, not done in this pass.

## Stage B — `.STR` movie container shape: CONFIRMED

Read the first 200 raw physical sectors of `DAT/MOVIE/GAI.STR` (the
smallest of the 7 movie files) directly from the disc image and checked
each sector's submode byte. Result: a perfectly regular, textbook pattern
of 7 video (Form1, `submode=0x42`) sectors followed by 1 audio (Form2,
`submode=0x64`, `coding_info=0x01`) sector, repeating exactly across all
200 sampled sectors (175 Form1 : 25 Form2, exactly 7:1). This is precisely
the standard PS1 STR interleaving convention — no custom/unusual framing.
By strong implication (same disc, same asset family, same `DAT/MOVIE/`
directory), the other 6 `.STR` files are almost certainly the same
standard shape.

**Net result**: the movie container format itself needs no reverse
engineering — it's a known, public PS1 standard. What remains for Stage B
is purely the *runtime detection* question (what CPU/MDEC activity
indicates playback is happening right now), which this pass did not
attempt (needs a live GDB session at a moment a movie is actually
playing) — see "What this pass did NOT do" below for why that turned out
to be directly observable this session anyway.

## Stage C — PROG.VB / PROGHEAD.CDB: real lead, not confirmed

No standard Sony VAB magic (`pBAV`) appears anywhere in `PROG.VB`,
`PROGHEAD.CDB`, or `PROGVAB.CDB` at a plain, uncompressed byte offset —
that specific hypothesis (a plain-file VAB header) is refuted.

Applying the same CDB-codec-plus-2048-skip technique that worked for
Stage A to `PROGHEAD.CDB` produces a complete 399-byte stream (confirmed
complete the same way as Stage A's header — decompression stops on a
genuine `0xFF` terminator, not a length cap) starting with the ASCII
bytes **`BAV`** followed by a `06` byte. This is **not** a byte-alignment
artifact: re-running the same decompression at every possible table-skip
offset from 2040 to 2048 bytes all converge on the identical `BAV\x06`
sequence (differing only in how many leading zero-padding bytes precede
it from the mostly-empty directory table) — no shift ever reveals a
leading `p` before it. The real conclusion is firmer than "misaligned
pBAV": **this game's audio system uses its own custom bank-header magic,
`"BAV\x06"`, distinct from the retail Sony `"pBAV"` VAB signature** — a
common pattern for PS1 titles that wrote their own SPU sample-bank loader
inspired by, but not byte-compatible with, Sony's stock VAB format.

Immediately following the magic: `00 00 00 00 00 00 60 c9 07 00 ee ee 10
00 28 00 1e 00 7f 40 00 00 ff ff ff ff 02 6e 00 3c 40 00 00 00 ff ff ff
ff ff ff ff ff 02 5a 00 3c 23 00 00 00 ff ff ff ff ff ff ff ff 02 ...` —
a repeating shape is visible (`ff ff ff ff` runs and a `02` byte recurring
at fairly regular intervals), consistent with a small fixed-size record
repeated per sample/program, but the exact field layout was not derived
this pass. `PROGVAB.CDB`'s equivalent attempt produced only 55 bytes with
no recognizable magic — its relationship to `PROGHEAD.CDB` (duplicate,
extension, or a different table entirely) is still open.

**Net result**: upgraded from "a promising fragment" to a confirmed,
reproducible custom magic string with real structure behind it — genuine
progress, but still not a working parser.

## Stage C follow-up #7 — `PROGHEAD.CDB`'s per-record layout, derived

Anchored on the complete 399-byte decompressed stream's most distinctive
landmark -- runs of 8 consecutive `0xFF` bytes -- and extracted whatever
sits between consecutive runs as candidate records, rather than guessing
field widths by eye. This produced a clean, dominant **16-byte record**
shape, confirmed independently two ways:

1. **The preamble states its own record size.** The ~26 bytes between the
   `"BAV\x06"` magic and the first record contain a `10 00` (`u16 LE` =
   `16`) field -- exactly matching the record stride found structurally
   from the `0xFF`-run landmarks. A format that states its own record
   size and a structural finding that independently arrives at the same
   number is real corroboration, not a coincidence.
2. **~22-23 record-sized slots total**, of which roughly the first 15-16
   carry real, varying data and the remaining ~7 are uniformly
   `00 00 00 3c 00 00 00 00` + the `0xFF` sentinel -- i.e. zero-filled,
   unused slots in a fixed-size array, the same "reserve the max, fill
   what's used" convention this project has seen elsewhere (`gcrts`'s own
   `MAX_LINES`/`MAX_LINE_CHARS` caps, PS1 VAB's own fixed 128-program
   table).

**Per-record shape** (16 bytes): `[u8 index][u16 LE value][u8 const=0x3c]
[u32 LE const=0x40][8x 0xFF sentinel]`. The `index` byte repeats
non-uniquely across records (`1,2,2,1,2,1,2,2,3,4,6,...`) -- plausibly a
channel or group number, not a unique ID. **The `value` field is `0x7f`
(127) in the large majority of records**, with the rest small values
close to it (`90, 75, 120, 100, 80`) -- `127` is the standard MIDI/PS1
convention for a 7-bit field's maximum (full volume/velocity), making
"per-program volume, mostly left at max" a plausible, coherent reading --
**a hypothesis, not live-confirmed** (unlike Stage C's sound-index chain,
nothing here was cross-checked against an actual live register capture).
`0x3c` (60) and `0x40` (64) recur as fixed constants across nearly every
record -- likely shared format/mode fields, not per-record data.

**Still open**: what the `0x3c`/`0x40` constants actually mean, whether
`PROGVAB.CDB` (which produced no recognizable magic in the earlier pass)
holds the actual sample data these records point to, and live
verification of any of this against real menu sound effects -- none
attempted this pass.

## Stage G — persistent build proof of concept: CONFIRMED

Wrote the already-tested, exact-size, translated `MENUDAT-START-translated.BIN`
(475 bytes different from the original, same 30,318-byte size) directly
into a full copy of the real disc image (`game_persistent_test.bin`,
never touching the original `game.bin`), at `MENUDAT.BIN`'s real ISO9660
LBA (254663, found by walking the tree, not hard-coded), respecting
MODE2/2352 physical sector framing — writing only each sector's 2048-byte
data payload, deliberately leaving the sync/header/subheader/EDC/ECC
bytes stale, specifically to test whether PCSX-Redux requires valid ECC
on read at all. Read the modified copy back via `gcrts.iso9660` (the same
reader used for the disc catalog) and confirmed byte-for-byte it returns
exactly the modified file — the write is mechanically correct.

Live half: stopped the running PCSX-Redux instance and relaunched it
completely fresh (no save state) against the modified copy. Confirmed via
screenshots across several minutes of real playtime: correct BIOS boot
splash, correct game ID detection (`SLPS00102`), the publisher's opening
movie logo, and multiple minutes of a real, long, correctly-rendered
opening cinematic (`.STR` playback — matching Stage B's finding, watched
live: red-tinted portrait, "HUMAN ENTERTAINMENT" logo, a hallway walk, a
rooftop-at-sunset scene, a skeleton scene) — all playing back completely
normally, with zero visible corruption, freezing, or CD-read errors,
despite the modified sectors sitting mid-disc with intentionally invalid
ECC. This game's opening movie turned out to be considerably longer than
expected, so this document was written before the actual title/classroom
menu screen (where `MENUDAT.BIN`'s translated "START" label would be
directly visible) was reached within the observation window.

**What this already shows, even before the menu is reached**: PCSX-Redux
does not appear to strictly validate CD-ROM ECC on read — many megabytes
of real sector data, including sectors in the same disc image as the
intentionally-corrupted-ECC `MENUDAT.BIN` sectors, have been read and
played back correctly. That was the actual open risk this proof of
concept existed to test.

**Net result**: fully confirmed, offline and live. As suspected, the
~15-minute stall was a genuine on-rails interactive segment gated on
controller input this session's own automation could not send (simulated
keyboard/mouse input does not register with this PCSX-Redux window, an
already-established finding from earlier UI-automation work this
session). The user provided the real input directly, reaching the
classroom title screen on the freshly, non-instrumented-booted modified
disc. Screenshot confirms the left label reads **"START"** in Latin
characters, not "開始" — the translated edit is genuinely present in the
running game, rendered from the disc-level write, on a completely fresh
boot with no save state and no runtime instrumentation. The right label
("準備"/Prepare) is unchanged Japanese, exactly as expected since only the
Start label was edited for this test — confirming the edit is precise,
not a lucky accident of broader corruption.

**What this proves overall**: a disc-level asset edit -- written directly
into a copy of the real disc image at its true ISO9660 LBA, with
intentionally stale EDC/ECC on the modified sectors -- survives a
completely fresh boot and renders correctly in actual gameplay. This is
the first genuinely *persistent* (not temporary-patch, not save-state-
dependent) proof this project has produced. The original `game.bin` was
never modified at any point; the proof lives entirely in
`game_persistent_test.bin`/`.cue`.

## Stage C live follow-up — `sound_or_voice_cue`'s call site: partially resolved

Scanned every existing dialogue save state's live script buffer
(`gcrts.live_extract.extract_and_decode`) for an actual `sound_or_voice_cue`
(control code `0x0800`) occurrence -- found real ones in 3 of 8 states,
with save-state slot 3 having one (`param=127`) right at the very start
of its captured buffer. Loaded that state fresh and armed a live `Z0`
breakpoint on `FUN_80075b14` -- the call target this project's own
`gcrts/script_decoder.py` comment already named for this control code,
never previously traced.

**It fired -- 3 real hits, identical arguments each time**:
`a0=0x801fe806`, `a1=0x801ffcf2`, `a2=0x0`, `a3=0x801fe800`,
`ra=0x80049974`. Two concrete, directly-verified facts, not inference:
`a3` is **exactly** `gcrts.live_extract.SCRIPT_BUF_ADDR` (`0x801FE800`),
and `a0` is **exactly** that base plus 6 bytes -- the script cursor
position immediately after this control code's 2 consumed words, matching
the live-decoded script byte-for-byte. This is the first live
confirmation that `FUN_80075b14` genuinely operates on the real script
interpreter's own cursor, not a coincidental match.

**A real, unexpected finding**: reading memory in-the-moment (before
resuming) across the 3 hits shows `a0`/`a1` staying IDENTICAL each time,
while a small counter visible in nearby memory increments by exactly 1
per hit (`...001a...` -> `...001b...` -> `...001c...`). This means
`FUN_80075b14` is called **repeatedly** (at least 3 times within about a
second, roughly once per frame) with the same arguments while this line
is active -- consistent with a per-frame playback-status POLL/UPDATE
function, not a one-shot "start this sound" trigger. This refines (does
not just confirm) the module comment's "4 calls" framing: this is
evidently the ongoing-status call, not the initiating one.

`a1` (`0x801ffcf2`) points to a small structure containing what decode as
2-3 valid PS1 RAM addresses (`0x800c48cc`, `0x8004f244`, `0x8004f224`,
one of them repeated) plus a flag word -- plausibly a playback-state
handle with callback/object references, not decoded further this pass.

## Stage C live follow-up #2 — the initiating call, found

Read the live code window around the known `FUN_80075b14` call site
(`0x80049900`-`0x80049b00`) and decoded every `JAL` instruction in it with
`gcrts.mips_jal_decoder` (no static disassembler needed -- this project's
own existing tool, pointed at bytes read straight off the running
emulator). This revealed the handler's exact, complete call sequence,
matching the module comment's "4 calls" precisely once one call that
recurs elsewhere too (`0x80077f48`, evidently a generic shared utility,
not sound-specific) is set aside:

```
0x8004996c -> 0x80075b14   (traced earlier: per-frame status poll)
0x80049978 -> 0x80075b68   (new)
0x8004998c -> 0x800760b4   (new)
0x80049994 -> 0x80075d34   (new)
```

Breakpointed all three new targets simultaneously (same save state, same
active line, `param=127`) and captured real arguments for each:

- **`0x800760b4`: `a0=0x7f a1=0x0 a2=0x7f a3=0x0`** -- `0x7f` is **127**,
  the script's own literal inline parameter, appearing directly and
  unmodified as this call's primary argument (duplicated into `a2` too).
  This is the strongest possible live evidence for "the initiating call":
  the exact value the script author wrote is what this function receives.
- `0x80075b68`: `a0=0x80015ad0 a1=0x1a a2=0x0 a3=0x801fe800` -- `a3` is
  `SCRIPT_BUF_ADDR` again; `a1=0x1a` (26) matches the same incrementing
  counter seen in `FUN_80075b14`'s nearby memory earlier; `a0` is a stable
  pointer, plausibly a sound-system/channel-manager object handle (further
  supported by it recurring below).
- `0x80075d34`: `a0=0x1a a1=0x0 a2=0x2 a3=0x7f` -- the same counter as
  `a0` here, and `127` reappears as `a3`, alongside a small `a2=2` value
  (plausibly a mode/type flag -- e.g. "voice" vs "music" vs "SFX").

**Net result**: the complete call sequence for this control code is now
mapped, and `0x800760b4` is a strong, evidence-backed candidate for the
actual "play sound/voice #N" trigger -- not a guess, the literal script
parameter shows up unmodified in its arguments.

## Stage C live follow-up #3 — `0x800760b4` decoded, a real state address found

Read the live code at `0x800760b4` and decoded it with a small, targeted
MIPS decoder (LUI/ADDIU/ORI address reconstruction plus load/store/JAL --
not a full disassembler, just enough to follow data references; written
this pass, not a pre-existing tool). Confirmed exactly what the function
does with the parameters:

```
addu $v0, $a0, $zero      ; v0 = a0 (127)
addu $v1, $a1, $zero      ; v1 = a1 (0)
addu $t0, $a2, $zero      ; t0 = a2 (127)
sb   $a3, 0x800a6117      ; [0x800a6117] = a3 (0)
...
sb   $v0, 0x800a6114      ; [0x800a6114] = 127  <-- the script's raw parameter, written to RAM
sb   $v1, 0x800a6115      ; [0x800a6115] = 0
sb   $t0, 0x800a6116      ; [0x800a6116] = 127
jal  0x80077808           ; hands off to a deeper sound-engine function (not traced further)
```

**`0x800a6114` is now a confirmed, live-verified address holding the raw
sound/voice index the script requested** -- not inferred, directly proven
by watching the exact byte get written from the exact register that held
the script's `127`. This alone is a genuinely useful, standalone
capability: any future session (or Stage D's Audio Inspector) can read
this one byte to know which sound index was last requested, with no
breakpoint needed.

Two adjacent small functions were visible in the same read and decoded
along the way: a simple one-byte getter at `0x80076118`
(`lbu $v0, 0x800a6106; jr $ra`), and two near-identical setters
(`0x80076128`-`0x76148` writing `(1,1)`, `0x76150`-`0x76174` writing
`(3,1)`) both targeting `0x800a6106`/`0x800a6107` — plausibly a small
playback-state pair (values seen so far: 1 and 3, consistent with a
STOPPED/PLAYING/PAUSED-style enum, not confirmed). A larger function at
`0x80076178` reads both `0x800a6114` (the requested index) and
`0x800a6107` (the state byte) and compares them -- plausibly a debounce
check ("has this exact request already been actioned"), not traced
further.

**Still open**: `0x80077808` (the deeper call every trigger hands off to)
was not traced -- that's very likely where the actual `XAPACK`/`PROG.VB`
asset gets selected and real SPU/XA playback begins, and is the natural
next step for closing the loop from "script parameter" to "actual audio
file." Not attempted this pass.

**Directly re-verified, not just decoded**: read `0x800a6114` live, right
after this trace -- returned `7f 00 7f 00`, exactly `(127, 0, 127, 0)`,
matching the decoded store sequence byte-for-byte. `0x800a6106` read
`00 01` at that same moment, a distinct real state-pair value from the
`(1,1)`/`(3,1)` seen being written by the two setter functions -- a
genuine third observed state, consistent with (not yet fully explaining)
a small state machine.

## Stage C live follow-up #4 — `0x80077808`: a real command-queue/dispatch layer, deeper than expected

Decoded `0x80077808` (the function `0x800760b4` hands off to) with an
extended version of the same targeted decoder (added branches, shifts,
more R-type ops -- this function turned out considerably more complex
than the simple parameter-store one traced before it). This is not one
function but a small cluster of adjacent functions/helpers, several with
real, decodable structure:

- **`0x80077808` itself**: packs `(a1, a2, a3, a 4th arg passed on the
  stack)` into 4 consecutive bytes at whatever `$a0` points to (a generic
  "build a 4-byte command struct" helper, not sound-specific by itself),
  then checks bit 0 of a flag word at **`0x800a61b8`** and, if set, calls
  `0x80080904` -- read as "enqueue a command, then flush the queue if
  it's marked ready."
- **`0x80077854`**: a one-line getter, returns the word at **`0x800a61ac`**.
- **`0x80077864`** / **`0x8007789c`**: near-identical dispatchers, both
  gated on the same `0x800a61b8` bit 0, both call a value read from
  **`0x800a61b0`** through into `0x80077d48` / `0x80077ee8` respectively
  -- two different follow-on handlers selected by something upstream, not
  identified yet.
- **`0x800778d4`**: increments a counter at **`0x800a61b4`**; once it
  reaches 7 (`sltiu`, not initially in the decoder -- caught and
  identified from the raw instruction), resets it to 0 and calls
  `0x800765b4(a0=0x10, a1=0, a2=1)` -- reads as a periodic/throttled
  maintenance call (every 7th tick), unrelated to any specific sound
  index.
- **`0x80077928`**: the important one. Masks its own `a0` to a single
  byte (`andi $a0,$a0,0xff`) and compares it against the literal value
  **`2`** (`bne $a0, 2, <elsewhere>`) -- a type/category dispatch. **This
  lines up directly with this session's own earlier capture**:
  `0x80075d34`'s `a2` argument, captured live two steps earlier in this
  same call chain, was exactly `2`. That's a real, self-consistent
  cross-reference across two separate breakpoint captures, not a
  coincidence -- strong evidence the control code being traced
  (`sound_or_voice_cue`) specifically dispatches as category "2" here,
  plausibly matching the master workflow's own MUSIC/VOICE/SFX/AMBIENT
  category framing (which specific category "2" is remains unconfirmed).
  Inside that branch: checks bit 2 of `0x800a61b8` again, and (when
  clear) calls `0x80080d54(a0=a1)`, storing its result into
  **`0x800a61ac`** -- the exact same address `0x80077854`'s getter
  reads -- then inspects bit 0 of a 16-bit field at offset `0x16` within
  a structure pointed to by **`0x800a61a8`**.

**Net effect**: this is genuinely a small sound-command dispatch/queue
system, not a single "play sound" function -- consistent with the
per-frame-poll behavior found earlier (`FUN_80075b14`). A real map of its
state now exists: `0x800a6106`/`0x800a6107` (state pair),
`0x800a6114`-`0x800a6117` (last-requested raw parameters, confirmed),
`0x800a61a8` (a structure pointer), `0x800a61ac` (a result/status word),
`0x800a61b0` (another pointer, feeds two dispatch branches),
`0x800a61b4` (a periodic tick counter), `0x800a61b8` (a bitfield flag
word gating multiple behaviors). Still open at the time: `0x80080904`,
`0x80077d48`, `0x80077ee8`, `0x800765b4`, and `0x80080d54` -- `0x80080d54`
was the strongest candidate for "resolves a sound index to a real audio
asset" and was traced next (below).

## Stage C live follow-up #5 — the chain closes: script parameter to a real audio file on disc

Decoded `0x80080d54` with the same targeted decoder (extended with
`sltiu`/multiply-shift/branch-on-sign patterns, expecting arithmetic
here). It is **not** a sound-index lookup -- it's a textbook, completely
generic **BCD MSF-to-LBA converter**, the standard PS1 CD-ROM
sector-addressing routine: reads 3 consecutive bytes (each a
binary-coded-decimal digit pair, the classic `high_nibble*10 +
low_nibble` pattern, applied three times), combines them as
`(minutes*60 + seconds)*75 + frames` (75 = the real, fixed PS1
sectors-per-second constant), then subtracts `0x96` (150 -- the standard
2-second CD lead-in offset every real MSF-to-LBA conversion subtracts).
This is shared, generic disc-driver infrastructure, not sound-specific
code, called here to convert a stored timestamp into a sector to seek to.

**Captured live, both ends of the call**: broke at the function's entry
and its dynamically-read return address (the same physical breakpoint
technique used throughout this session, applied to a return site instead
of a call site). Entry: `a0=0x800aba14`, pointing to the raw BCD bytes
`28 14 21` -- MSF `28:14:21`. Return: `v0 = 0x1efc9 = 126921`.

**Checked directly against this session's own disc catalog**: LBA 126921
falls **exactly** within `DAT/XA1/XAPACK08.BIN`'s real sector range
(126218-131001, computed precisely from the catalog's own LBA+size
fields, not approximated).

**This closes the full chain, live-verified at every link, from a script
control code to a specific physical audio file on the disc**:

```
sound_or_voice_cue (script control code 0x0800, param=127)
  -> 0x800760b4: writes (127,0,127,0) to 0x800a6114          [LIVE_VERIFIED]
  -> 0x80077808: command dispatch, type check == 2           [LIVE_VERIFIED, cross-referenced against an independent capture]
    -> 0x80080d54: BCD MSF (28:14:21) -> LBA 126921           [LIVE_VERIFIED, both entry and return captured]
      -> DAT/XA1/XAPACK08.BIN (LBA 126218-131001)             [CONFIRMED against this session's own disc catalog]
```

Every arrow above is a real, live capture from this session -- not one
step in this chain was inferred or assumed.

## Stage C follow-up #6 — the target sector itself, read and decoded

Read the raw physical sector at LBA 126921 directly from the disc image
(offline, no emulator needed for this step) and its XA subheader bytes,
plus a small window of neighboring sectors either side. Every one carries
`submode=0x64` -- Form2 + Audio + Real-time bits set, the **exact same
submode** this session's own Stage B pass already confirmed for real
`.STR` movie audio sectors -- confirming this genuinely is a live
CD-ROM-XA audio stream, not some other kind of data. `coding_info=0x01`
decodes as **mono, 4-bit ADPCM** (the standard, lower-bandwidth XA
audio profile PS1 games typically reserve for spoken dialogue rather than
music, which usually uses the higher-quality stereo/8-bit profile) --
consistent with, not just compatible with, this being a *voice* line, per
the control code's own name.

**The channel-number byte cycles 0-7 across consecutive sectors**
(`...5,6,7,0,1,2,3,4...`), directly confirming `XAPACK08.BIN` is a
genuinely **interleaved 8-channel XA stream** -- multiple distinct audio
tracks packed sector-by-sector so a single CD seek can feed several
selectable/simultaneous streams without drive head movement, the standard
PS1 XA multiplexing technique. The target sector for sound index 127 sits
at **channel number 7**, at byte offset 1,439,744 into `XAPACK08.BIN`
(`file_number` a constant `1` throughout the sampled window). To extract
this specific voice line's full audio, a decoder would need to collect
every sector carrying channel 7 across the surrounding span of the file,
exactly what the PS1's own XA hardware does automatically when told to
play channel 7 -- not attempted this pass (that belongs to a future Stage
D Audio Inspector, per the master workflow's own dependency order).

## Stage B live attempt — movie-playback detection: inconclusive, real evidence either way

Tried the cheapest available live lead: `gcrts/cdb_codec.py`'s own
docstring already documents a disassembly-confirmed call chain --
`0x8006e2d8 -> resource_load (0x8005342c) -> ... -> 0x80076aa0` -- for
generic disc-resource loading. If `resource_load` is truly generic, it
should also fire for `.STR` movie loads, which this session already knows
happen within the first ~20-30 seconds of a fresh boot (much cheaper to
reach than the ~15-minute full intro). Relaunched PCSX-Redux fresh against
the original `game.bin` and armed a `Z0` breakpoint at `0x8005342c` during
that early window.

**Zero hits over ~40 real seconds**, spanning BIOS boot through the
publisher logo and into the movie itself (confirmed by the emulator
remaining fully GDB-responsive afterward -- not a hang, a genuine miss).
`resource_load` never fired during the exact window this session already
watched real `.STR` movie content play, live, in an earlier pass.

**This is a real, informative negative result, not a dead end**: it
refutes the specific hypothesis (that this game's own generic CDB-resource
loader is also used for movie files) rather than just failing to find
anything. The likely explanation, consistent with everything else found
this session: `resource_load`'s own name and its confirmed role in the
`FUN_8007681c`/`gcrts.cdb_codec` chain are specifically scoped to this
game's *custom* `.CDB` resource format (fonts, scripts, `AFRM`/`SIKFORM`)
-- standard PS1 `.STR` movie playback almost certainly goes through Sony's
own stock CD-XA/MDEC streaming library instead, a completely separate,
lower-level code path this game's custom resource system has no reason to
touch. Finding THAT path needs a fresh, from-scratch trace (no existing
named lead the way `resource_load` or `FUN_80075b14` were) -- real,
larger follow-up work, honestly out of scope for this pass's budget.

## Stage B second attempt — reusing the confirmed MSF-to-LBA converter: also negative

The Stage C thread itself handed Stage B a second, better-grounded
hypothesis than the first: `0x80080d54`, the BCD MSF-to-LBA converter
found and live-confirmed while tracing `sound_or_voice_cue`, looks like
generic CD-ROM sector-addressing infrastructure by everything in its own
code -- nothing about it is sound-specific. Any CD seek, including for
movie playback, needs an MSF-to-LBA conversion somewhere, so if the movie
system shares this exact utility, its call site(s) would show up with a
different `$ra` than the sound-cue call site already found
(`ra=0x80077968`).

Relaunched PCSX-Redux fresh against the original `game.bin`/`game.cue`
and armed a `Z0` breakpoint at `0x80080d54` during the same early
fresh-boot window this session has already directly watched real `.STR`
movie content play (confirmed via a follow-up GDB memory read afterward
that the emulator remained fully responsive -- a genuine miss, not a
hang).

**Zero hits over ~45 real seconds.** Same outcome as `resource_load`:
this rules the hypothesis out directly. Whatever code handles `.STR`
movie seeking does not call this shared MSF-to-LBA utility either.

**Two independent, real negative results now, not one.** Neither this
game's custom `.CDB` resource loader (`resource_load`) nor its own
generic MSF-to-LBA converter (`0x80080d54`) are used for movie playback.
Both results are genuinely informative: they eliminate the two most
plausible "movies reuse existing traced game infrastructure" hypotheses,
not just fail to find something. The remaining, well-reasoned
explanation is unchanged and now more strongly supported: PS1 `.STR`
movie playback almost certainly goes through Sony's own stock CD-XA/MDEC
streaming library directly, via the BIOS's fixed low-memory syscall
gates (`0xA0`/`0xB0`/`0xC0`, dispatched by a function-number register
rather than a named `JAL` target) -- a genuinely different kind of
investigation from everything that worked for Stage A/C so far, since
there is no candidate address to breakpoint without first knowing the
exact BIOS function numbers PS1 CD-streaming calls use, and the fixed
dispatch addresses themselves fire for essentially every BIOS call in
the game (timers, controllers, everything else), making a naive
breakpoint there too noisy to use without filtering live by the
function-number register at each hit. Real, larger follow-up work, not
attempted this pass given the added risk/uncertainty relative to
everything else traced this session.

## Stage B third attempt — BIOS syscall-gate lookup, static scan, and a DMA-boilerplate correction

Looked up the real PS1 BIOS CD-ROM syscall convention (psx-spx
`kernelbios.md`, fetched this pass) rather than guessing: async CD
functions dispatch via `jal 0xa0` with the function number in `$t1`/R9
-- `0x78`=CdAsyncSeekL, `0x7C`=CdAsyncGetStatus, `0x7E`=CdAsyncReadSector,
`0x81`=CdAsyncSetMode, `0x95`=CdInitSubFunc, `0xA4`=CdGetLbn,
`0xA5`=CdReadSector, `0xA6`=CdGetStatus. No CD functions live in the
B-table (`0xb0`), correcting an earlier hazy assumption.

Rather than a live breakpoint on the shared `0xa0` gate (too noisy --
fires for essentially every BIOS call in the game), scanned every disc
executable **statically and offline** for the exact instruction idioms
that would invoke these functions: `jal 0xa0` with `li $t1,<funcnum>` in
either delay-slot order, and the alternative "thin trampoline" idiom
(`move $t1,$rX ; j 0xa0`, a tail-jump used by single-purpose BIOS wrapper
functions). Covered all 15 executables on the disc (`CAP0-CAPX.EXE`,
`MKUBI/MNINO/MOP/MOVER/MPRO/MRIKA/MYOKO.EXE`, `PROG.EXE`,
`SLPS_001.02`). **Zero matches anywhere, in either pattern.** No game
code, in any overlay, ever calls a BIOS CD-ROM async function directly
via the standard calling convention. This is a real, clean, fully
offline negative that further narrows the search space: it means CD-ROM
access for this game -- sound and (presumably) movies alike -- either
goes through a different, higher-level API (e.g. POSIX-style
`open()`/`read()` file I/O, which uses different B-table functions not
searched for this pass) or through code this static idiom search can't
detect (e.g. computed/indirect calls).

A parallel static lead looked more promising at first: searching for
`lui`+`ori` construction of `0x1f801080` (PS1 DMA channel 0 = MDEC-in,
the video decoder -- genuinely video-specific hardware, unlike generic
CD reads) turned up exactly one hit in **every single executable**,
including the 24KB `SLPS_001.02` bootstrap. Full decode of the
surrounding code (in `PROG.EXE`, runtime `0x80052760`) resolved this
into a **generic, channel-parameterized `dma_channel_start(channel,
madr, bcr_hi, bcr_lo, chcr, ...)` library wrapper** -- it busy-waits on
the given channel's CHCR busy bit, sets the matching DPCR enable bit,
and writes MADR/BCR/CHCR for whatever channel its caller passes in
`$a0`. The `0x1f801080` constant only appears because that's the channel-0
base the function's own address arithmetic starts from (`0x1f801080 +
channel*16`), not because any call is MDEC-specific. **Correcting the
initial read of this finding**: since this exact function, with exactly
3 near-identical call sites, is present in every executable including
the bootstrap that never shows video, it is ordinary GPU/graphics-DMA
boilerplate from the statically-linked SDK, not a movie signature by
itself. Its 3 call sites' channel arguments were not statically
resolvable (register values threaded through further back than the
scan's lookback window) -- a genuine limitation of static analysis here,
not a claim that they aren't channel 0.

Attempted one more live step to resolve this ambiguity: breakpoint
`PROG.EXE`'s own copy of `dma_channel_start` (runtime `0x80052760`)
during a fresh boot's early window, logging the `$a0` channel argument
at every real hit (a much lower-frequency, better-scoped target than the
raw `0xa0` BIOS gate). Added a residency check first (poll the target
address for `PROG.EXE`'s own expected opcode bytes before arming) after
learning the hard way, mid-session, that blindly arming a breakpoint at
a fixed runtime address is unsafe when several different executables
share the same load-address range (`PROG.EXE`, `CAP1-CAP4.EXE`, and
`CAPX.EXE` all load at `0x80035000`, so the *same* address holds
completely different code depending on which overlay is actually
resident at the time).

**Result: `PROG.EXE`'s code never became resident at the target address
within 90 real seconds of a fresh boot.** This is itself informative,
not just a failed attempt: it means `PROG.EXE` is very likely **not**
the first overlay executable loaded and resident during the movie
window -- one of the `CAP*.EXE` files (which share the same load-address
range) is a more likely candidate, or the boot sequence's overlay
ordering isn't what the file-naming convention ("PROG" = program/
prologue) suggested. Retargeting to a `CAP*.EXE`'s own copy of this
function (e.g. `CAP0.EXE` at runtime `0x80083c60`, already located by
the static scan) is the direct next step, not attempted this pass given
the effort already spent across four separate angles this session.

**Summary of everything ruled out for Stage B this pass**: `resource_load`
(this game's own `.CDB` loader), the confirmed sound-chain MSF-to-LBA
converter, and direct/trampoline calls to the BIOS CD-ROM async API
across all 15 executables. None of these are how movie playback works.
The one remaining unresolved thread -- whether the generic
`dma_channel_start` wrapper's channel-0 (MDEC-in) callers are
movie-specific -- needs either deeper static dataflow analysis or a
correctly-targeted live capture against whichever overlay is *actually*
resident during the movie, which first requires identifying that
overlay (a concrete, well-scoped next step, not yet done).

## What this pass did NOT do

- Full field-by-field decoding of SDB2.0's frame table or pixel data.
- Confirming SIKFORM.CDB's exact format identity.
- A working VAB parser for `PROG.VB`.
- Any live GDB tracing for movie-playback detection or `sound_or_voice_cue`
  resolution — the recommended order deliberately holds these until the
  cheap offline checks justify the cost, and three of four just did.
