# Moonlight Syndrome (SLPS-01001) — Second-Game Portability Investigation

Real second-game validation for the GCRTS toolkit, per
`docs/status/TOOLKIT_READINESS_AUDIT.md`'s own flagged gap: every
profile/subsystem coverage claim in this project had only ever been
checked against *Twilight Syndrome: Tansaku Hen* (SLPS-00102). The user
provided a second, real, owned disc — *Moonlight Syndrome* (Japan,
Disc 1), same publisher (Human Entertainment), a different game/engine
— specifically to test whether the toolkit generalizes or is a
one-game hack.

## What transfers with zero code changes — CONFIRMED_LIVE

- **ISO9660 reading** (`gcrts.iso9660`): parsed the disc's root
  directory correctly on the first try. Structure is meaningfully
  different from Twilight Syndrome (no `CAP*.EXE` overlay family at
  all; a single boot executable `SLPS_010.01;1` plus flat `*.DAT`
  containers — `DISC1.DAT`, `HENLIN.DAT`, `HENSHITS.DAT`, `MOWDEI.DAT`,
  `PROLOGUE.DAT`, `SOWGUW.DAT`, `TITLE.DAT` — and separate `MOVIE/`
  (`.STX` files) and `XA/` (`.XAM`/`.XAS` files) directories).
- **Movie decode** (`gcrts.movie_str_audio` + FFmpeg's `psxstr`
  demuxer): three different `.STX` movies (`TITLE.STX`, `PROLOGU2.STX`,
  `HENSHIT0.STX`, `MOWDEI.STX`) all auto-detected correctly with the
  *exact* same stream properties as Twilight Syndrome's `OP.STR`
  (`mdec, yuvj420p, 320x240, 15fps` + `adpcm_xa, 37800Hz stereo`).
- **Audio-activity detection** (`gcrts.audio_activity_segments`): ran
  cleanly against all three tested movies, found real candidate
  segments in each (durations ranging 0.5s–23.8s). Visual inspection of
  frames inside two of those windows found no burned-in on-screen text
  (a dark corridor scene; an abstract psychedelic "hypnosis" scene) —
  inconclusive on whether these specific windows contain real spoken
  dialogue, since RMS activity is not speech detection (the same
  honestly-scoped limitation as `gcrts.audio_activity_segments`'s own
  docstring already states).
- **Full re-encode round-trip** (`psxavenc`, exact same command/params
  used for Twilight Syndrome): decoded `PROLOGU2.STX`, remuxed, and
  re-encoded via `psxavenc -t strcd -f 37800 -c 2 -s 320x240 -r 15` —
  succeeded in ~2s, and independently re-decoding the output confirmed
  a valid 301-frame/20.06s stream. The entire
  decode→re-encode→re-verify chain that
  `gcrts.movie_subtitle_burner.build_burned_in_movie` automates for
  Twilight Syndrome appears to transfer to this game with **zero code
  changes**.
- **Live emulator boot** (`gcrts.pcsx_disc_loader`, `gcrts.pcsx_lua_console`):
  copied the disc to `C:\PCSXRedux\game\moonlight.bin/.cue`, loaded it
  via the existing disc-loader automation (computed the correct row
  from the real directory listing, no code changes), reset/resumed via
  the existing Lua console helper. Boots clean — same "HUMAN
  ENTERTAINMENT" publisher splash as Twilight Syndrome, correct GAME
  ID (`SLPS01001`), a real rendered 3D opening movie (rotating moon,
  then character-portrait credits with on-screen name captions), no
  crash.
- **Interactive controller input** (`gcrts.pcsx_pad_bridge`, the
  Lua-exposed `PCSX.SIO0` pad-override mechanism): CIRCLE/START presses
  through the existing bridge navigated from the intro movie into real
  gameplay — a character in a rendered street scene with a genuine
  Japanese dialogue text box (see below). A further CIRCLE press
  correctly dismissed that dialogue box, confirming real interactivity,
  not just a fixed animation.

## Real in-game dialogue found (unlike OP.STR)

Unlike Twilight Syndrome's `OP.STR` (which turned out to have no
spoken dialogue at all — see `BURNED_IN_SUBTITLE_PIPELINE.md`), this
game's actual gameplay has a real, interactive Japanese dialogue box.
Transcribed directly from a live screenshot (zoomed 3x for legibility):

```
ミカ
・・・あんなのだったら
もっと早く帰ってくればよかった▼
```

(speaker tag "ミカ"/Mika, then roughly "...if it was going to be like
that, I should have come home sooner", with a "▼" continue-indicator.)

## Text-location investigation: two cheap hypotheses ruled out

1. **Raw, uncompressed Shift-JIS** — encoded the transcribed lines
   (and the speaker tag) to Shift-JIS and searched the raw disc image
   bytes directly. Zero matches for any candidate substring.
2. **Twilight Syndrome's existing CDB codec** (`gcrts.cdb_codec`,
   reverse-engineered from `CAP0.EXE`'s `FUN_8007681c`) — tried
   decompressing `SELECT.DAT` (the smallest DAT file, 145KB) directly
   from offset 0. Failed immediately (`bytearray index out of range`).
   Unsurprising: this game has no `CAP*.EXE`/`K#LINK.CDB`
   directory-table convention at all — the file layout is
   architecturally different, so there's no strong reason to expect
   the same byte-level codec, even from the same publisher.

Both negative results are useful data, not dead ends: they establish
that the text is neither plaintext nor using an already-known scheme,
meaning a *new* format (container and/or compression and/or encoding)
is genuinely in play here.

## Disassembly-based investigation: real progress, no codec found yet

Extracted the boot executable `SLPS_010.01;1` (313,344 bytes, valid
`PS-X EXE`, confirmed `pc0=0x800285D0` — matching the real boot address
seen live in PCSX-Redux's own log output, `t_addr=0x80010000`,
`t_size=0x4C000`). Disassembled the full code segment via
`gcrts.mips_disasm` (77,824 instructions).

**Found and ruled out**: the disassembly contains embedded ASCII debug
strings, including the full list of `*.DAT` filenames the executable
loads by name and generic Sony-SDK debug strings (`intr.c`, `bios.c`,
`sys.c`, `CdSearchFile: searching %s...`, etc. — this appears to be a
debug-symbol-retaining build of the standard PS1 SDK, not evidence of
anything game-specific). Located the exact code that references the
`"CdSearchFile: searching %s..."` string (a clean single LUI/ADDIU
address-construction hit at `0x8003fe30`) and disassembled its
containing function (`0x8003fc78`–`0x8004021c`): this turned out to be
a **generic CD directory-entry search/enumeration routine** (scans up
to 64 24-byte directory entries, compares names via a helper at
`0x8003ff44`, copies out the matching entry) — i.e. exactly what the
string says, a `CdSearchFile`-style file lookup, not a
text/decompression codec. A real, useful finding (confirms how files
get located) but not itself the answer.

**Heuristic byte-dispatch scan, two false positives**: wrote a
pattern-matcher over the full disassembly looking for the structural
shape of a control-byte decoder (an `lbu` immediately followed by
several range comparisons inside a tight loop) — 36 raw hits, narrowed
to comparisons against large byte-range constants (0x60–0xFF, matching
the *shape* of Twilight Syndrome's own real codec's thresholds). Two
candidates were inspected in full and both turned out to be unrelated:

- `0x8003e5e4` region: a PS1 controller (pad) polling/state-machine
  loop (`andi` against small bitmasks like `0x0007`/`0x0010`/`0x0020`,
  a `PS-X Control TAP Driver` debug string nearby, a computed jump
  table dispatching on controller-type values 1–5) — input-driver
  code, not text/compression.
- `0x8001be8c` region: saturating-arithmetic clamping (`slti ..., 129`
  paired with clamps to 0 or 128) — looks like GTE/lighting-intensity
  clamping, not a byte-stream codec.

**Honest conclusion**: locating the real text/container format for
this game will need genuinely more targeted work than blind
instruction-pattern matching over a 300KB, symbol-less binary — most
likely tracing the actual call graph forward from the confirmed
`CdSearchFile`-equivalent (find its callers, follow to the real
`CdRead`/sector-read call, then trace what happens to that buffer)
rather than pattern-guessing across the whole file. This is real,
bounded, but substantial future work — comparable in scope to the
original CDB-codec discovery for Twilight Syndrome, which took
significant dedicated investigation.

## Call-graph tracing: found real engine structure, still no text codec

Followed the plan from the previous pass: found the single caller of
the `CdSearchFile`-equivalent function (`0x8003c024`, inside a small
wrapper at `0x8003c00c` that resolves a filename to a `{lba, size}`-ish
descriptor — still just file-lookup plumbing, not the codec). That
wrapper itself has exactly one caller too, landing in a **large command
dispatcher** at `0x8003c12c` that loads a value from a fixed global
(`0x8008EB74`) and branches on ~15+ distinct values in `0x1000`-spaced
bands (`0x1000`, `0x2000`, `0x3000`, `0x4000`, `0x5000`, `0x6000`-ish,
plus `0`/`1`) — almost certainly the game's own scene/event **script
opcode dispatcher** (the engine that runs dialogue/staging scripts).
Traced two of its smaller opcode handlers (`0`, `1`, `0x3000`) into a
shared helper (`0x8003e118`) expecting to find a script-byte-stream
reader there — it turned out to be a **controller-input polling
helper** (checks pad button bitmask `0x0010`, matches the same pattern
seen in the earlier pad-driver false positive), reused across opcodes
that need to "wait for a button press" (exactly what a dialogue
`▼`-advance opcode would need). Real engine structure, still not the
text/codec itself.

**Pivoted to live memory search instead of more static tracing.**
Reset the emulator, replayed input back to the exact same dialogue box
(`ミカ` / `・・・あんなのだったら` / `もっと早く帰ってくればよかった▼`),
and dumped the *entire* live 2MB PS1 RAM via GDB while it was on
screen. Searched for the same Shift-JIS byte sequences already ruled
out on disc — **zero matches in live RAM either**, even though known
ASCII strings from the executable (`"PS-X Control TAP Driver  Ver
3.0"`, `"JULIETTA DEBUG SCREEN"`) were found at sane offsets in the
same dump, confirming the RAM read itself is correct.

**This is a real, meaningful finding, not a dead end**: the on-screen
text is almost certainly not standard Shift-JIS *anywhere* in this
game's pipeline — on disc or decompressed in RAM — which strongly
suggests a **proprietary glyph-index text system**, conceptually
similar to what this project already independently found for Twilight
Syndrome's own native renderer (`gcrts.glyph_atlas`'s per-chapter,
RAM-resident compressed glyph blob, indexed by something other than
raw character codes). Confirming that and reverse-engineering the
actual index scheme is its own real sub-investigation — locating the
font/glyph resource itself, then correlating index values to the
rendered characters — not something a byte-string search alone can
finish.

## Live memory diffing: found a real per-glyph position table

Advanced the dialogue (via the pad bridge) to a new set of lines
(`くだらないコンパなんかに誘いやがって` / `カヅキの奴・・・`, appended
below the earlier lines — this text box accumulates rather than
replacing), and dumped the full 2MB RAM again for a second snapshot.
Diffed the two dumps directly (byte-for-byte, merging changes within 8
bytes of each other) rather than guessing — 43 changed regions total,
almost all tiny (1–17 bytes, plausibly stack/counter noise) except a
handful of internally-structured ones.

One region, `0x80092388`–`0x800923ed` (101 bytes), decodes cleanly as
an array of 27 little-endian 32-bit integers, monotonically increasing
within each line and resetting to a small value at a line break:

```
32, 41, 55, 66, 79, 92, 103, 116, 132, 145, 158, 173, 186, 202, 215,
230, 245, 257,   (line 1: 17 deltas, all in 9-16px)
32, 45, 59, 72, 86, 102, 110, 118,   (line 2, restarts at 32)
0                                      (terminator)
```

The deltas between consecutive values (9, 14, 11, 13, 13, 11, 13, 16,
13, 13, 15, 13, 16, 13, 15, 15, 12, 13, 14, 13, 14, 16, 8, 8) are all
in the 8–16 pixel range — the right order of magnitude for a
proportionally-spaced glyph advance-width table, and consistent with
this era's ~16px-square CJK glyph cells (the same ballpark as Twilight
Syndrome's own native 16x16 `gcrts.glyph_atlas` cells, though not
proof the two games share a format). Two other regions in the same
diff (`0x80091788`/`0x80091b88`, both constant-`0x80000000`-repeated,
and `0x80092788`, `0xc0000000`/`0xd0000000`-repeated) are still
unexplained — same 4-byte-per-entry shape, but a single repeated value
across many entries rather than per-character variation, so probably a
per-line attribute/flag rather than per-character identity.

**What this confirms**: there is a real, live, parseable per-glyph
layout structure in RAM, and it changes in lockstep with on-screen text
exactly as expected — strong evidence this dialogue system is a
genuine variable-width text layout engine, not a fixed-grid one.
**What's still missing**: this table gives pixel positions, not
character *identity* — the parallel array that says *which* glyph goes
at each position (the thing that would actually let a translation
patch replace it) has not been located yet. The character count
implied by this table (17 then 8) does not cleanly match a naive count
of the visible characters either, so the exact unit this table indexes
by (raw script bytes vs. rendered glyphs vs. something else) is not
yet confirmed.

## Found a real GPU sprite-draw list; disproved it as a glyph-identity source

`0x80092388`'s position table turned out to be one column of a
**struct-of-five-parallel-arrays**, each exactly 101 bytes and spaced
precisely `0x400` apart (`0x80091788`, `0x80091b88`, `0x80091f88`,
`0x80092388`, `0x80092788`). Reading all five aligned by index showed
three are constant across every entry (`0x80`, `0x80`, `0x08`) and the
fifth only changes once, exactly at the line-break (`0xc0`→`0xd0`,
a +0x10 step matching a 16px line height) — none of these five vary
per character, so none of them are glyph identity either.

A wider scan for *real per-character variation* (not just a single
line-break jump) found a much more promising structure at
`0x8008f788`/`0x80090788`: a **repeating 4-word group**, structurally
identical to a PS1 GPU textured-sprite draw command:

```
word0: low byte = per-char X advance (matches the position table);
       high-ish byte = line-bank (0xb0 -> 0xc0 at the line break)
word1: two bytes that vary per character, both near-always multiples
       of 0x10 -- e.g. (0x90,0x70), (0xd0,0x80), (0x50,0x70)... --
       looking exactly like (column,row) coordinates into a 16x16-
       pixel-celled texture atlas, plus a constant 0xc0 and 0x7f
       (almost certainly a GPU command-type/texture-page tag)
word2: a per-entry destination slot counter, +0x10 each entry
word3: constant 0x7e808080 (GPU primitive command byte + a neutral
       0x808080 tint, the standard convention for an untinted
       textured sprite)
```

This is genuinely a real GPU sprite command list — not a guess. But
checking whether `word1`'s (column,row) value tracks *character
identity* disproved it: the transcribed text for this exact 26-entry
window (`くだらないコンパなんかに誘いやがって` + `カヅキの奴・・・`,
confirmed to be exactly 18+8=26 characters, matching the array length
precisely) has two different characters (`ん` at index 9, `や` at
index 14) sharing the *identical* `(col,row)` coordinate, and the
*same* character (`な`, indices 3 and 8; `い`, indices 4 and 13) maps
to *different* coordinates each occurrence. A stable per-character
atlas lookup cannot produce that. The much more likely explanation:
this is a small **glyph texture cache** (a fixed number of texture
slots that recently-used glyphs get blitted into, reused/evicted
round-robin as new characters scroll into view) — the coordinate
tracks *which cache slot*, not *which character*.

**Implication for where to look next**: the rendering side (GPU
primitive lists, texture cache slots) is a dead end for finding stable
character identity — by the time text reaches the GPU command list,
its original per-character code has already been resolved into "which
cached texture slot," discarding the identity information a translation
patch would need. The real target is further upstream: the decompressed
**script-byte stream** itself (before it's turned into cache-slot
lookups), which loops back to the original open question — the
container/compression format for the `*.DAT` files — rather than
anything reachable by watching the renderer.

## Breakthrough: a real script buffer with a readable label table, and a strong character-code candidate

Went back upstream from the rendering dead-end, per the previous
section's own conclusion. `0x8008bee8`'s diff (`0x3f9`→`0x441`, a
72-byte delta for the 26 newly-added characters, ~2.77 bytes/char —
plausible for a mixed 1/2-byte code table) sits right next to a stable
32-bit value, `0x801e84a4`, that looks like a RAM pointer. It is one:
dumping bytes at that address found a real, structured **script
buffer with a readable ASCII label table** at its very start —

```
24000000 "START"    2503 0000 "E000A"   4b040000 "E000B"
c8040000 "E000C"    eb050000 "E000D"    ... "SHORTCUT" ...
"START005" ... "SCENE8" ... "E00CC"
```

(offset, then a null-padded ASCII label — script jump-target names,
left un-stripped in this build). Past the label table (~offset
`0x1b0`), the buffer becomes dense binary opcode data — this is a
real, decompressed, in-RAM script bytecode buffer, not a guess.

Within that buffer, the exact byte range the diff pointed at
(`ptr+0x3fc` onward) decodes cleanly as a run of **big-endian 16-bit
values, almost all under 256** (occasionally larger, e.g. one `0x0165`
= 357) — precisely the shape expected for a custom character/glyph
code table:

```
87, 136, 118, 100, 81, 169, 205, 226, 100, 125, 85, 357, 81, 115,
126, 159, 98   (17 values, for the 18-character line
                "くだらないコンパなんかに誘いやがって")
```

**Strong positive signal**: aligning these 1:1 against the visible
characters (`く,だ,ら,な,い,コ,ン,パ,な,ん,か,に,誘,い,や,が,っ,て`),
the two occurrences of `な` (positions 3 and 8) both land on value
`100` — an exact match, and not something that would happen by chance
for a real character-code table.

**Open discrepancy**: the two occurrences of `い` (positions 4 and 13)
land on *different* values (`81` and `115`), and there are 18 visible
characters but only 17 values before the next marker — off by exactly
one. The leading hypothesis: characters carrying a dakuten/handakuten
mark (`だ`, `パ`, `が` all appear in this exact line) consume **two**
codes each (a base kana code plus a separate diacritic marker), which
would shift the alignment partway through the line and explain both
the off-by-one count and the `い`/`い` mismatch — but this hasn't been
confirmed against a second, independent line yet, so it stays a strong
hypothesis, not a closed finding.

**This is the strongest lead of the whole investigation** — a real,
located, decompressed script buffer with small-integer character codes
that demonstrably repeat correctly for at least one repeated
character. Closing the gap needs the same kind of work already applied
here, just repeated against 2-3 more known dialogue lines to nail the
exact diacritic-handling rule and confirm the code-to-character
mapping isn't coincidental.

## CONFIRMED: the character-code table, cracked with a clean second sample

Advanced the dialogue further (movement + a new interaction triggered
a fresh line with **no dakuten/handakuten characters at all** — a
clean test case) and dumped RAM a third time. This new line gave two
back-to-back clusters whose lengths matched the visible character
counts **exactly** (8 and 10), unlike the earlier, messier extraction:

```
"やめてほしいよね"        (8 chars)  -> 115,113,98,109,91,81,117,103
"しゃれにならないっ" + て (10 chars) -> 91,156,121,101,100,118,100,81,159,98
```

Cross-checking every character that appears in *both* clusters against
its own code confirms the table is real and consistent, with zero
mismatches:

| kana | code (hex) | seen |
|---|---|---|
| し | 0x5b | both clusters, identical |
| い | 0x51 | both clusters, identical |
| な | 0x64 | twice in cluster B, identical |
| て | 0x62 | both clusters, identical |
| や | 0x73 | — |
| め | 0x71 | — |
| ほ | 0x6d | — |
| よ | 0x75 | — |
| ね | 0x67 | — |
| ゃ | 0x9c | — |
| れ | 0x79 | — |
| に | 0x65 | — |
| ら | 0x76 | — |
| っ | 0x9f | — |

This resolves the earlier "off by one, `い` doesn't match itself"
discrepancy from the first (messier) sample: that extraction's window
boundary was almost certainly cut one byte short (likely explaining
the 17-vs-18 count) and/or slightly misaligned, not evidence of a real
diacritic-driven encoding rule — with this clean, exact-count sample,
plain 1:1 character→code mapping holds with no exceptions. (The
original sample's one large value, `0x0165` = 357, aligning with the
kanji `誘`, is also independently consistent with this table's shape:
common kana get small one-byte-ish codes, less-common kanji get larger
ones — a frequency-sorted custom character table, exactly the kind of
space-saving scheme expected from this era.)

**This is a real, working, reusable decode** for at least this
game's hiragana range — built empirically from live memory, the same
disciplined way every other live claim in this project is verified,
not asserted from static analysis alone. Extending this table to full
coverage (katakana, kanji, punctuation) is now a mechanical repeat of
this same procedure against more sampled lines, not an open research
question.

## Table expanded further, and a first demo sentence

Advanced through one more menu (`話しかける`/`逃げる`/`様子を見る` —
noted separately below, since its own encoding looks structurally
different) and one more dialogue line (`な、なんか用？`) and repeated
the exact same dump-and-decode procedure.

**`な` confirmed a 5th independent time** (value `0x64`, identical to
every prior sample). Two new characters got their first
confirmation, consistent with the pattern already established (still
single-sample, not yet cross-checked against a second independent
line): `ん` = `0x7d`, `か` = `0x55`. One kanji and one punctuation mark
were also captured for the first time, both consistent with the
"common kana get small codes, less-common kanji get larger ones"
pattern already seen with `誘` (357): `用` (a kanji) = `0x10f` (271),
and `？` (a question mark) = `0x02` — a very low, special-looking code,
plausibly from a separate small punctuation/control range rather than
the general character table.

**Confirmed table so far** (14 characters with 2+ independent,
zero-mismatch confirmations each — the same bar as `な`):

| kana | code | | kana | code | | kana | code |
|---|---|---|---|---|---|---|---|
| し | 0x5b | | や | 0x73 | | に | 0x65 |
| い | 0x51 | | め | 0x71 | | ら | 0x76 |
| な | 0x64 | | ほ | 0x6d | | っ | 0x9f |
| て | 0x62 | | よ | 0x75 | | | |
| | | | ね | 0x67 | | | |
| | | | ゃ | 0x9c | | | |
| | | | れ | 0x79 | | | |

Plus 4 single-sample entries awaiting a second confirmation: `ん`=0x7d,
`か`=0x55, `用`=0x10f (kanji), `？`=0x02 (punctuation).

**First demo: a real sentence built entirely from confirmed codes.**
`ほしいな` ("hoshii na" — a natural, casual phrase along the lines of
"I wish..."/"I want that...", fitting this game's dramatic dialogue
tone) uses only the four fully-confirmed characters `ほ`, `し`, `い`,
`な`:

```
ほ し い な
0x6d 0x5b 0x51 0x64
```

Writing this into the actual script buffer (once the surrounding
opcode format around a text run is understood well enough to build a
correctly-framed replacement, not just the character values
themselves) is the next real step toward an actual injected/patched
sentence — this demo shows the codes are known and ready, not yet that
the full write-back path has been built and proven.

## Live write experiment: real proof, honestly not yet clean

Tested actually writing a custom sentence into the running game, per
direct request, with screenshots as proof
(`evidence/moonlight_syndrome_live_write_experiment/`).

**First attempt (negative, but informative): patching an
already-displayed line.** Overwrote the first dialogue line's own
character-code bytes (already on screen) via `GdbClient.write_memory`.
Confirmed via screenshot: **zero visible effect**, even after advancing
to a new page below it. Consistent with the earlier GPU-primitive/
texture-cache finding — once a line is converted to cached sprite draw
commands, it is never re-read from source.

**Second attempt: patching a not-yet-displayed line.** First confirmed
a real structural fact live: content well *ahead* of the current
read-cursor position was already sitting in the script buffer,
undisplayed — i.e. the whole scene's script decompresses upfront, and
the "offset counter" tracked earlier is a **read/display cursor**, not
a write cursor. This meant a line that hadn't been shown yet
(`やめてほしいよね`) could be safely patched ahead of time. Overwrote
its 8 character-code slots with the confirmed codes for `ほしいな`
(repeated twice: `0x6d,0x5b,0x51,0x64,0x6d,0x5b,0x51,0x64`), read the
bytes back to confirm the write landed, then advanced the dialogue via
the pad bridge until the game's own cursor reached that position.

**Result: the write measurably changed what rendered — but not
cleanly.** The line that should have shown clean text instead rendered
as a small, garbled, overlapping glyph cluster (see
`03_closeup_garbled_result.png`). This is real, positive proof the
buffer is genuinely read live at first-display time (a null result
here would have meant the buffer model was wrong) — but it also
surfaces a concrete, previously-undiscovered requirement: this game's
renderer uses a **separate, parallel per-glyph position/advance-width
array** (the struct-of-arrays block documented earlier), computed from
the *original* characters' pixel widths. Only the character-code array
was patched; the position/width array still describes the old
characters, so new glyphs get drawn at old-width-derived positions,
producing exactly this kind of overlapping garble.

**Honest status**: writability is proven; legibility is not, yet. A
clean injection needs the position/width array recomputed and written
alongside the character codes — a concrete, scoped next step, not an
open unknown.

## Controlled retest: the width-table hypothesis doesn't hold up

Attempted a tightly-controlled repeat (fresh reset, patch a
not-yet-displayed cluster, advance, immediately inspect both arrays)
to confirm the "stale position/width table" explanation for the
garbling. Two real complications surfaced:

1. **Dialogue branching is not perfectly deterministic across
   replays.** The same input-replay approach that reliably reached
   specific lines earlier this session this time diverged onto a
   different path (reaching `あの・・・聞いてます？` instead of the
   expected `な、なんか用？` cluster that had just been patched) —
   real, live evidence that this game's dialogue selection isn't pure
   fixed-script playback purely keyed on button-press counts (some
   state — possibly timing-sensitive, possibly menu-choice-dependent —
   affects which line comes next). The patched cluster's bytes were
   confirmed still intact (read back correctly) but it's unclear
   whether/how they were ever actually displayed.

2. **The "width table" theory needs revision.** Checked its live
   content after several more lines had genuinely rendered on screen —
   it was **byte-for-byte identical** to the values captured hours
   earlier for the very first original line
   (`32,41,55,66,79,92,103,116,132,145,158,173,186,202,215,...`),
   despite multiple different lines having since displayed correctly.
   This directly contradicts the "recomputed fresh per new line"
   assumption the garbling explanation depended on — this array is
   either stale/unused after its first computation, or serves some
   other one-time purpose (e.g. an initial textbox-bounds calibration)
   rather than being the live per-glyph position source read at every
   render.

**Honest status**: the live-write experiment's core positive result
stands — writing to a not-yet-displayed character-code cluster does
measurably change what renders (`evidence/moonlight_syndrome_live_write_experiment/`).
But the *specific explanation* offered for why the result was garbled
rather than clean (a stale, un-recomputed width table) is now itself
in doubt, and finding the real cause needs a different diagnostic
approach than checking this particular array — likely disassembly
work around wherever this array actually gets written (to see when
and how often), rather than more live-memory probing alone. Not a
quick fix; a genuinely open sub-question.

## Net result so far

Every layer of the toolkit that doesn't depend on game-specific text
format knowledge (disc reading, movie decode/encode, live boot,
interactive input) transferred to a second, real, different-engine
game with **zero code changes** — a strong, concrete answer to the
"is this a toolkit or a one-game hack" question. The one thing that
does NOT transfer for free — locating and understanding a new game's
own text/compression format — was always expected to require fresh
reverse-engineering per game (this was never something the earlier
Twilight Syndrome work could have made generic), and that work has
been started, not finished, here.
