# SPU-Side XA Playback Discovery

Milestone goal: stop chasing the CD-ROM command side (exhausted across
the previous five audio milestones — `ReadS` never observed, the
traced `ReadN`/Setmode cycle ruled out, and a second full-RAM
pointer-value scan on the CD-ROM side found only interrupt/DMA
infrastructure). Pivot direction: `audible event -> SPU state/register
activity -> writer -> audio subsystem -> upstream source`. New module:
`gcrts/spu_audio_path.py`, `tests/test_spu_audio_path.py` (15 tests).

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

## Actual playback backend

Per the milestone's required taxonomy (`gcrts.spu_audio_path.PlaybackBackendClassification`):
**`UNKNOWN`** (`classify_playback_backend()`). `CD_init` is a real,
live-firing, structurally strong candidate — it is, so far, the single
strongest concrete lead across all thirteen audio milestones this
project has run. It is not upgraded to `XA_ADPCM_CONFIRMED` or
`CD_INPUT_UNKNOWN_FORMAT` because:

1. Its SPUCNT/CD-Volume/Main-Volume writes were never once observed to
   persist on a later read — every subsequent check, in both sessions,
   found all three back at `0x0000`/`0x00000000`.
2. No single capture window combined an armed breakpoint on `CD_init`
   (or the Key ON sites) with a user confirming, in the same instant,
   that real audible dialogue was playing.

Per this milestone's own explicit instruction, evidence outranks
architectural expectation — this stays `UNKNOWN` rather than guessed
past what was actually caught live.

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

**566 passed** (551 baseline + 15 new in `test_spu_audio_path.py`), no
regressions. Full suite run via `pytest tests/` (the repo root also
contains several unrelated, pre-existing scratch/temp directories from
prior sessions that pytest's default collection cannot access on this
Windows environment — a pre-existing, unrelated condition, not
introduced by this milestone; scoping collection to `tests/` avoids it
the same way prior sessions have).

## Remaining blocker

No capture session has yet combined an armed breakpoint on `CD_init`
or a real Key ON site with the user confirming, at that exact instant,
that audible dialogue is playing — every prior "we heard a sound"
confirmation in this project's history came from live chat during an
unrelated capture, not a session built around these specific new
addresses.

## Next milestone

Run a session where these exact breakpoints (`CD_init`'s SPUCNT write,
both real Key ON sites) are armed first, and only then have the user
trigger and immediately confirm a real audible dialogue line — closing
the one gap left in this pass's otherwise-strong `CD_init` lead.
