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
