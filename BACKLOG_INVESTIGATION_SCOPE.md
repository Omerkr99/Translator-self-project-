# Backlog Investigation Scope

Scoping pass over the 7 milestones' own backlog (complex image formats,
movie/audio/subtitle runtime detection, persistent build) — none of it
has an implementation yet, per the workflow's own instruction to keep
architecture compatible but not start until explicitly directed. This
document is that scoping: what's actually known right now, what the
cheapest real next step is per area, what tools already exist to reuse,
and what "worth pursuing further" would look like. No code was written
against any of this; the one piece of real work done to inform it was
producing `DISC_FILE_CATALOG.md` (a full, real disc listing via the
already-existing `gcrts.iso9660` walker — read-only, no assumptions).

That catalog changes the starting position for three of these areas
substantially: Stage B (movies) had *zero* known movie files as of the
last audit; there are 7. Stage C (audio) had one unresolved script
control code as its only lead; there are now two structurally distinct
candidate sound systems (43 `XAPACK*.BIN` streaming files, and a
menu-owned `PROG.VB`/`PROGHEAD.CDB` VAB-shaped pair). Stage A (complex
image formats) had no candidate files at all; there are now two
(`AFRM.CDB`, `SIKFORM.CDB`), one already sitting extracted on disk from
a prior session.

## Stage A — Complex Image Formats (SDB2.0 / SDB2.2 / MS4 / GP4)

**Known**: explicitly unsupported, explicitly never located anywhere in
this game's data as of the last full audit (`IMAGE_FORMAT_ADAPTERS.md`,
`GCRTS_FULL_SYSTEM_AUDIT.md` §20). The already-solved MENUDAT/PROGDAT
assets were specifically confirmed to be ordinary TIM, not SDB — a
negative result for those two files, not for the whole game.

**New this pass**: `DAT/HITO/AFRM.CDB` (5.97MB) and `DAT/HITO/SIKFORM.CDB`
(4.9MB) are large, unclassified `.CDB` files — the leading candidate
location. `AFRM.CDB` is already extracted byte-exact
(`C:\PCSXRedux\afrm_full.bin`) from prior work, never parsed past that.

**Cheapest real next step** (fully offline, no PCSX-Redux, no new
extraction): try `gcrts.cdb_codec`'s decompressor and the same
2048-byte/512-entry directory-table convention `K0LINK.CDB`/`KFONT.CDB`
use (`gcrts/cdb_codec.py`, `README.md`'s K0LINK section) directly against
the already-extracted `afrm_full.bin`. Three honest outcomes, not just
one: (a) table+codec both apply, decompressed entries decode as a
recognizable structure (frame dimensions, a repeating small-record
pattern, or a TIM-like header via the existing TIM detector) — real
progress; (b) table format applies but the codec doesn't (garbage after
decompression) — means AFRM uses the CDB *container* convention but its
own payload codec, a distinct, smaller reverse-engineering task; (c)
neither applies — AFRM isn't shaped like the other CDB files at all, and
the investigation moves to raw structural analysis (repeating record
sizes, embedded palette-shaped byte runs) the same way MENUDAT/TIM was
originally found.

**If that stalls**: the proven live technique from `K0LINK.CDB`'s own
history — a GDB breakpoint on the shared decompressor call chain
(`0x8006e2d8` → `FUN_8007681c`, already found and documented) while
whatever code loads `AFRM.CDB` actually runs — would give a live,
disassembly-grounded answer instead of guessing. Not attempted yet;
listed as the fallback because it requires reaching an in-game moment
that actually uses this file, not yet identified.

**Exit criteria for "worth building an adapter"**: at least one AFRM/SIKFORM
entry decodes into a recognizable raster (even a crude one) or a
structured record set with an internal shape that repeats sensibly across
entries. If it never does, downgrade back to explicitly unsupported and
move on — do not force a partial adapter no data confirms.

## Stage B — Movie Runtime Detection

**Known before this pass**: nothing. The prior audit's explicit answers
were "no" to every question (is a movie playing, which one, what time) —
not because it was hard, but because nobody had confirmed movie files
existed on this disc at all.

**New this pass**: 7 real `.STR` files in `DAT/MOVIE/` (`GAI`, `KIKU`,
`KUBI`, `NINO`, `OP` — 47.7MB, almost certainly the opening — `PRO`,
`YOKO`). `.STR` is a standard PS1 container (MDEC video sectors
interleaved with XA-ADPCM audio sectors at fixed sector granularity) —
this is a well-documented, generic PS1 format, not something specific to
this game that has to be reverse-engineered from nothing.

**Cheapest real next step** (offline): read raw sectors of the smallest
file (`GAI.STR`, 3.1MB) via `gcrts.cdrom`'s existing sector-level access
and check whether the submode/coding-info bytes alternate between video
(Form1) and audio (Form2) in the pattern real `.STR` files use — this
either confirms or refutes "this is a standard STR file" cheaply, before
any live emulator work.

**Runtime-detection-specific next step** (needs PCSX-Redux, not yet
attempted): a live GDB session started right at game boot (the opening
movie is the one moment guaranteed to trigger movie playback without
needing to navigate anywhere) watching for MDEC register writes or a
`StRead`/`StGetNext`-shaped BIOS call pattern — the standard way PS1
games drive `.STR` playback. No hypothesis about the exact call site
exists yet; this is a from-scratch trace, unlike Stage C's `sound_or_voice_cue`
head start.

**Scope reminder**: this stage's deliverable is *detection* (which movie,
roughly when) — not movie editing, not a movie player, matching the
milestone's own explicit framing.

**Exit criteria**: one live-confirmed signal (a register write, a call
site, anything) that reliably correlates with "a movie is currently
playing" and can distinguish at least two different `.STR` files from
each other.

## Stage C — Runtime Audio Detection

**Known before this pass**: one named-but-unresolved script control code,
`sound_or_voice_cue` (`0x0800`, `gcrts/script_decoder.py`), calling
`FUN_80075b14` with an inline parameter never traced. No audio files
known to exist; the "sound" entries in the asset registry
(`sound.sculpture_hall`, etc.) turned out to be *image* labels for a
sound-menu, not audio data.

**New this pass**: two structurally distinct sound systems, not one —

1. `DAT/XA1/`+`DAT/XA2/`: 43 `XAPACK*.BIN` files, ~230MB, sequential and
   size-descending — shape strongly suggests streaming XA-ADPCM audio
   (voice/BGM), matching the volume of content a per-location "voice"
   system (the MENUDAT sound-menu labels) would need.
2. `DAT/SINKOU/PROG.VB` + `PROGHEAD.CDB` + `PROGVAB.CDB` — smaller,
   menu-executable-owned, shaped like a standard Sony **VAB** sample bank
   (`.VB` = VAB body is a real, documented Sony extension, not a guess).
   This is the more tractable target: VAB is a fully public, standard
   format (fixed header layout, VAG-ADPCM samples) — parsing it needs
   format knowledge, not reverse engineering, if `PROGHEAD.CDB` really is
   (or substitutes for) the missing VAB header.

**Cheapest real next step** (fully offline): attempt a standard VAB parse
of `PROG.VB`/`PROGHEAD.CDB` first — cheapest possible win, since success
needs no live emulator and no disassembly, only correctly matching a
public format's header layout. Separately, read one `XAPACK` file's first
few sectors and check for the same Form2/audio submode signature Stage
B's `.STR` check would establish, to confirm or refute "these are raw XA
audio" before investing further.

**The one piece that connects audio to the *script* (needed later for
Stage F)**: a live GDB breakpoint on `FUN_80075b14` during a real
dialogue line already known to have an associated voice cue — resolving
what its inline parameter actually selects (a sound_or_voice_cue index
into one of the two systems above) is the concrete next live step, not
yet attempted.

**Exit criteria**: at least one successfully extracted, actually-playable
audio sample (a VAB SFX or an XA audio chunk), plus — separately — a
resolved meaning for `sound_or_voice_cue`'s parameter on at least one real
example.

## Stage D — Audio Inspector

Blocked on Stage C actually producing extractable audio; not
independently investigatable before that. Once extraction exists, the
inspector itself is architecturally closer to a mechanical UI build
(mirroring `asset_inspector_ui.py`'s structure — waveform/preview instead
of image preview, a play button instead of an overlay editor) than a
reverse-engineering task. Not scoped further here; revisit once Stage C
has a real extracted sample to build against.

## Stage E — Subtitle System

Blocked on both Stage B and Stage C producing stable, addressable event
IDs (a movie needs an identity before a cue can reference "at this movie,
this timestamp"; same for voice). No data model exists yet
(`GCRTS_FULL_SYSTEM_AUDIT.md` §25 confirmed this directly — not merely
undocumented, actually absent). Pure data-model design once B/C exist;
nothing to investigate before then.

## Stage F — Pause-to-Subtitle Workflow

Depends on B, C, D, and E all existing first. The one piece already
built and ready to receive this: Milestone 6's `RuntimeSnapshot`
(`gcrts/runtime_snapshot.py`) already declares `active_movie`/
`active_audio` fields, always empty, specifically so this stage can start
populating them later without changing the snapshot's shape. Nothing else
to scope until the earlier stages land.

## Stage G — Persistent Build

Independent of B through F — could be investigated any time, and is
arguably the most self-contained of the whole backlog. Current state:
temporary PCSX-Redux CD-file patching is proven and reliable; writing a
real, persistent BIN/CUE is not implemented anywhere in `gcrts`
(`GCRTS_FULL_SYSTEM_AUDIT.md` §30).

This session's disc catalog makes the smallest real end-to-end proof of
concept concrete: `DAT/SINKOU/MENUDAT.BIN` — an asset this project
already knows how to edit and rebuild at the *exact* original byte size
(`AssetProject`'s exact-size policy) — has a known LBA and size in the
real disc image. The next real step is: take a copy of `game.bin`, write
an already-tested modified `MENUDAT.BIN` build back into that exact byte
range, and confirm the resulting image still boots and plays correctly in
PCSX-Redux from a **fresh, non-instrumented load** (not a temporary
in-memory patch). Because this asset stays within its original byte
budget by construction, this specific proof of concept sidesteps the
harder unsolved sub-problems (CDB resize, sector/extent relocation)
entirely — it's a real test of "can this project produce a truly
persistent disc," not a claim about arbitrarily-sized edits.

**Exit criteria**: one modified `game.bin`, byte-identical to the original
outside the one edited range, that PCSX-Redux boots and plays correctly
from a completely fresh load.

## Recommended order

Cheapest and most independent first, live/expensive work only once the
cheap checks justify it — matches this project's own established
"detect first → understand → edit → automate" discipline:

1. **Stage G's minimal proof of concept** — fully offline except for one
   final PCSX-Redux boot-and-play check; turns an already-solved edit
   into a genuinely persistent one, independent of everything else.
2. **Stage C's `PROG.VB` VAB parse** — cheapest possible real audio win;
   standard format, no live emulator, no disassembly if the format guess
   holds.
3. **Stage A's `AFRM.CDB`/`SIKFORM.CDB` codec/table trial** — also
   fully offline, already-extracted data, reuses existing code unchanged.
4. **Stage B's `.STR` sector-shape check** — cheap, offline, answers
   "is this really a standard STR file" before any live tracing.
5. Only after 2–4 produce something real: the live GDB work each implies
   (movie-playback register tracing, `sound_or_voice_cue` resolution,
   and any AFRM-specific live trace if the offline codec trial fails).
6. **D, E, F** stay unscoped until their prerequisites land — attempting
   to design them now would be designing against nothing real yet.
