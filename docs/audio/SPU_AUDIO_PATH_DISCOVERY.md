# SPU-Side XA Playback Discovery

Milestone goal: stop chasing the CD-ROM command side (exhausted across
the previous five audio milestones — `ReadS` never observed, the
traced `ReadN`/Setmode cycle ruled out, and a second full-RAM
pointer-value scan on the CD-ROM side found only interrupt/DMA
infrastructure). Pivot direction: `audible event -> SPU state/register
activity -> writer -> audio subsystem -> upstream source`. New module:
`gcrts/spu_audio_path.py`, `tests/test_spu_audio_path.py` (23 tests
after the follow-up Live Audible Trigger Correlation experiment,
below).

## SPU pointer scan

A full 2MB live-RAM raw-value scan for `0x1F801C00` (the SPU base
address) found **7 pointer-holder addresses**, all confirmed live to
hold that exact value: `0x8001587C`, `0x800A30CC`, `0x800A32C0`,
`0x800A38A8`, `0x800A3BCC`, `0x800A3BD0`, `0x800A3BDC`. `0x800A30CC`
sits immediately adjacent to the already-known, already-understood
CD-ROM 4-register pointer block (`0x800A30BC`-`0x800A30C8`) — the
highest-priority lead, followed first.

## Audible control

Static tracing from `0x800A30CC` found a function at
`0x80081B04`-`0x80081BCC`, identified by the game's own debug string a
few instructions earlier in the same function: `"CD_init:addr=%08x\n"`.
It:

- reads Current Main Volume L/R (`+0x1B8`/`+0x1BA`); sets Main Volume
  L/R (`+0x180`/`+0x182`) = `0x3FFF` only if not already nonzero
- unconditionally sets CD Volume L/R (`+0x1B0`/`+0x1B2`) = `0x3FFF`
- unconditionally sets SPUCNT (`+0x1AA`) = `0xC001`

Per public psx-spx documentation (confirmed via WebSearch this pass),
**SPUCNT bit 0 is "CD Audio Enable" (0=Off, 1=On), controlling both
CD-DA and XA-ADPCM streaming into the SPU's mixed output**. `0xC001`
has that bit set. This is exactly the kind of anchor this milestone
asked for: real code, live-confirmed to run, that directly manipulates
the one documented hardware bit governing whether CD-sourced audio
(including XA-ADPCM) reaches the speakers at all.

`CD_init` was confirmed live across two separate capture sessions:

| Session | Duration | Hits | Interrupts seen |
|---|---|---|---|
| `m14_arm_spucnt.py` (SPUCNT/CD-Vol/Main-Vol writes armed) | ~560s | 18 (6 full firings x 3 writes) | 3961 |
| `m15_combined_watch.py` (armed alongside Key ON/OFF sites, below) | 300s | 0 | 5430 |

A full-RAM writer scan for SPUCNT's offset (`+0x1AA`) across all 7 base
holders found **9 static call sites into `CD_init`**: `0x80080428`,
`0x80081308`, `0x80081548`, `0x80081928`, `0x80081D28`, `0x80081E50`,
`0x80082064`, `0x800824F0`, `0x80082724`. The inconsistency between the
two sessions (fires reliably in one, not once in the other, despite
both starting from the same save-slot-9 reload) means `CD_init` is
conditional on some game state not yet isolated — not a guaranteed
per-load event, and not yet caught in the exact instant of a
user-confirmed audible moment.

## Silent control

The same `+0x1AA` writer scan found a second, much larger family: 17 of
the 18 total SPUCNT writer sites cluster around base `0x800A38A8`,
spanning `0x8008E748`-`0x80090A14` (~9 KB of code). Direct disassembly
of the first site (`0x8008E744`-`0x8008E7D0`) shows a generic
read-AND-clear/delay-loop/read-OR-restore pattern touching bits `0x8030`
— explicitly **not** bit 0 (CD Audio Enable). This reads as a
general-purpose SPU control/reset utility used broadly across the
game's whole SPU subsystem (voices, reverb, etc.), not something
CD-audio-specific. None of this family's sites fired in any live
capture this pass.

## SPU hardware writes

Summarized in `gcrts.spu_audio_path.SPUCNT_WRITER_SITES` /
`KEY_WRITER_SITES` — every site found, its base-pointer family, and
whether it has fired live, each with a real evidence string (tested
never to be empty).

## CD input state

`CD_init`'s CD-Volume write (`+0x1B0`/`+0x1B2` = `0x3FFF`) is
unconditional, same function, same 6 confirmed firings as SPUCNT. No
independent CD-input-specific state beyond SPUCNT bit 0 and CD Volume
was found this pass.

## Voice activity

A writer scan for SPU Key ON (`+0x188`) / Key OFF (`+0x18C`) found 5
real sites: a pair at base `0x800A32C0` (`0x800866A0`/`0x800866A8`,
single call site `0x8008664C`), and three at base `0x800A38A8`
(`0x8008E934`, `0x8008E9D8`, `0x8008EB84`).

Live-armed for 300s (`m15_combined_watch.py`), across a real
save-slot-9 reload:

- `0x800A32C0`'s pair fired constantly — 2657/2659 hits, ~9.5 Hz,
  consistent with a per-tick housekeeping sync call.
- **5312 of 5316 total hits across both registers carried `a0=0x0`**
  — an empty voice bitmask, a no-op. The only nonzero hits (`a0=0x4`
  then `a0=0x3`) both landed within 4 seconds of the state-slot load —
  far more consistent with a UI/menu confirmation blip than a
  sustained dialogue-voice segment, and not confirmed against a real
  heard sound.
- The `0x800A38A8` Key ON/OFF sites never fired at all in this session.

This is a genuine, honest negative result for "ordinary SPU voice
playback," not proof it never happens — only that it did not happen,
with a real nonzero bitmask, during this particular 300-second capture
window.

## DMA-transfer activity

Not investigated this pass — out of scope once the CD_init/Key-ON
comparison above became the priority per the milestone's own "stop
broad scanning once a strong writer family is found" instruction. Left
open for a follow-up.

## Follow-up: Live Audible Trigger Correlation experiment

Closed the exact gap the original pass left open. Used the project's
own established automated-input technique (`Keyboard_PadCircle` =
`0x44`/'D', the confirmed advance/confirm binding from `pcsx.json`) to
trigger dialogue deterministically from save-slot 9, with
`CD_init`'s SPUCNT write and all 5 known Key ON/OFF sites armed
*before* the trigger — `gcrts.spu_audio_path.LIVE_CORRELATION_RUNS`.

**Decisive result (run 2):** the user explicitly confirmed hearing a
real voice line during the exact ~24-second captured window.
`script_parameter`/`position_counter`/`source_file` genuinely changed
across that window (`XAPACK42.BIN@182935` → `XAPACK20.BIN@158842`),
proving the automated input reached the game. **Zero of the 6 armed
sites fired meaningfully**: `CD_init`'s SPUCNT write never fired at
all; the `0x800A32C0` Key ON/OFF pair fired 814/815 times, every one
`a0=0x0` (no-op); the `0x800A38A8` family never fired. Per this
milestone's own Phase 8: **audible playback in this observed instance
is not triggered through any of these known SPU writer sites at event
start.** This is a genuine, decisive, CPU-register-level-confirmed
negative result — `live_correlation_confirmed_audible_with_zero_known_hits()`
→ `True`.

### A second, independent finding: the SPU MMIO read/write channel itself is unreliable

Attempting Phase 9/10 (poll the full SPU register block — all 24
voices + control registers, 640 bytes — during the confirmed-audible
window) found **zero byte-level change across the entire block for the
whole session**. Before trusting that as a real result, a direct
diagnostic was run: write `0x3FFF` to Main Volume via GDB, then read
it back, **while independently verified to be genuinely, continuously
running** (RAM position counter climbing every second under a
corrected continue-loop that properly re-issues `c` after every
PCSX-Redux interrupt-halt). The write did **not** round-trip — readback
was `0x0000` immediately and still `0x0000` a full second later. Plain
RAM writes round-tripped correctly in the same session, and the KSEG1
uncached mirror (`0xBF801D80`) showed the identical stuck-zero
behavior, isolating the problem to the SPU hardware I/O address range
specifically. **`gcrts.spu_audio_path.spu_mmio_read_write_roundtrip_reliable()`
→ `False`** — a confirmed tooling limitation, not a game-behavior fact.

This *reclassifies* the original pass's "the write does not persist"
finding: it was never established that `CD_init`'s write fails to
persist on the real emulated hardware — only that this project's
chosen read channel cannot verify it either way. The same caveat
applies retroactively to every "SPU register reads back 0" observation
across this whole investigation. Findings based on **CPU register
reads** at breakpoint hits (the value actually loaded into `$v0`/`$a0`
at the write instruction) remain fully valid — that read path has been
reliable throughout this entire project, unaffected by this finding.

## Actual playback backend

Per the milestone's required taxonomy (`gcrts.spu_audio_path.PlaybackBackendClassification`):
**`UNKNOWN`** (`classify_playback_backend()`) — but now for a stronger,
more precise reason. A real capture window WAS achieved this
follow-up: armed breakpoints on every known SPU writer site, a real
automated trigger, and explicit user confirmation of audible dialogue
in that exact window. None of the known sites fired — `CD_init` and
both Key ON/OFF site families are decisively ruled out as the
mechanism for that instance. What actually IS responsible remains
unknown, compounded by the confirmed inability to directly verify true
SPU hardware register state through this project's GDB-based read
channel. Per this milestone's own explicit instruction, evidence
outranks architectural expectation — this stays `UNKNOWN` rather than
guessed past what was actually caught live.

## XAPACK correlation

Not newly re-established this pass; the prior chain
(`script_parameter -> ScriptUnit fingerprint -> selector table ->
XAPACK file/LBA`, `AUDIO_CONTEXT_RESOLUTION.md`/`XA_STREAM_RESOLUTION.md`)
is unaffected by this milestone's findings and remains the
project's confirmed source-resolution path. This milestone did not
trace forward from a specific XAPACK-resolved event into a live
`CD_init` firing in the same window — a natural next step, not yet
done.

## Runtime integration

None added this pass. Per the milestone's own Phase 18-19 instruction,
`gcrts.audio_playback_truth`'s `AudiblePlaybackState` is intentionally
left unchanged (still only `UNKNOWN`) — no new evidence-backed value
exists yet to add.

## Tests

**574 passed** (566 baseline + 8 new in `test_spu_audio_path.py`, now
23 total in that file), no regressions. Full suite run via
`pytest tests/` (the repo root also contains several unrelated,
pre-existing scratch/temp directories from prior sessions that
pytest's default collection cannot access on this Windows environment
— a pre-existing, unrelated condition, not introduced by this
milestone; scoping collection to `tests/` avoids it the same way prior
sessions have).

## Remaining blocker (superseded)

This section originally read: "This project has no working channel to
directly verify true SPU hardware register state." **Resolved** by the
follow-up `SPU_OBSERVATION_CHANNEL.md` milestone: PCSX-Redux ships a
native, built-in SPU debugger (`Debug > SPU > Show SPU debug`) that
reads the emulator's own true internal state, bypassing GDB entirely.
Cross-checked at the same live instant: it showed `CTRL=0xC081` (CD
Audio Enable bit set) while GDB's own read of the same register showed
`0x0000` — confirming GDB specifically fails on SPUCNT, and reversing
this document's own "the write does not persist" finding above:
`CD_init`'s effect genuinely IS live on real hardware; only GDB's read
of it was wrong. See `SPU_OBSERVATION_CHANNEL.md` for the full
methodology, validation, and the honest limits of what this new
channel could and couldn't establish (background-music channels being
active in every "silent" baseline prevented isolating one specific
dialogue-voice channel this pass).

## Next milestone

Find or construct a scene/state with genuinely no background
music/ambience active, then repeat the silent-vs-audible SPU Debug
comparison (`SPU_OBSERVATION_CHANNEL.md`) to isolate the one channel
(if any single channel) responsible for dialogue playback.
