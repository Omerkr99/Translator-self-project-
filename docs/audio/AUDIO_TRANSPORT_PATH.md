# CD Input Data-Path Identification

Milestone goal: stop chasing "prove XA-ADPCM" through Setmode/`ReadS`
(both exhausted — see `SPU_AUDIO_PATH_DISCOVERY.md`) and instead answer
a more fundamental question: **what data actually feeds the CD Input
path during a confirmed audible voice line?** Investigate the transport
itself — DMA, buffers, SPU routing — without assuming a format up
front. New module additions: `gcrts/spu_audio_path.py`'s
`TransportPath`/`StreamFormat` model, `tests/test_spu_audio_path.py`
(10 new tests).

## Current confirmed source chain

```
script cue → ScriptUnit → selector → selector table → XAPACK source file → real disc LBA
```

Three independent resolution mechanisms agree. Unaffected by this
milestone; not reopened.

## DMA evidence

PCSX-Redux's own `Debug > Misc hardware > Show HW Registers` window
(found by inventorying the Debug menu rather than assuming raw GDB
MMIO was the only option) exposes all 7 system DMA channels'
`MADR`/`BCR`/`CHCR` plus the 3 hardware timers, reliably and without
the GDB SPU-MMIO unreliability documented elsewhere in this chain.

With a save state positioned right at a confirmed voice-line moment,
and the emulator verified genuinely, continuously running (Timer 1's
own counter changed on every one of 25 captured frames — an actual
elapsed-time signal, not just an "interrupts happened" proxy):

| Channel | Role | MADR/BCR/CHCR across the whole window |
|---|---|---|
| DMA3 | CD-ROM | **Byte-identical, zero change** |
| DMA4 | SPU | **Byte-identical, zero change** |
| DMA2 | GPU | Real transfer-completion pattern observed mid-capture (`MADR` → `0xFFFFFF`, `BCR` → `0`, `CHCR` status bit shifted) |

The GPU channel's real activity in the same captures is the control
that rules out "the emulator was just frozen" as an explanation for
the CD-ROM/SPU channels' silence — genuine execution and genuine DMA
activity were both happening throughout, and neither the CD-ROM nor
SPU DMA channel participated in it at all.

## Silent comparison

Not run as a separate baseline capture this pass — the CD-ROM/SPU
channels' values were also confirmed static in an earlier same-day
capture taken before the emulator was verified running (a methodology
error, caught and corrected: without genuine execution nothing would
be expected to change regardless of audio). The corrected, running
capture is the one reported above.

## SPU RAM behavior

Not directly inspected this pass — the PS1 SPU's internal 512KB RAM is
not part of the CPU's normal address space and isn't reachable through
either the (already-unreliable) GDB MMIO path or the HW Registers
window. Left open; see Next milestone.

## CD transfer behavior

DMA3 (CD-ROM)'s `MADR` never moved, so there is no runtime transfer to
compare against the resolved XAPACK LBA this pass — a genuine negative
result in itself, not a gap in observation.

## RAM staging buffers

Not searched for this pass, since the DMA finding already answers the
"how does it physically move" question at the level this project's
current tooling can observe (see Playback backend below) — no evidence
pointed toward a RAM staging/ring-buffer structure to trace.

## Decoder / transformation

Not located this pass.

## Playback backend

`classify_playback_backend()` stays `CD_INPUT_UNKNOWN_FORMAT` — the
DMA finding does not change this legacy combined classification, but
substantially narrows what "CD input" means in practice.

**New, separated model** (per this milestone's own explicit
instruction not to collapse routing and format into one enum):

- `classify_transport_path()` → `TransportPath.DIRECT_HARDWARE_AUDIO_BUS`
  — by elimination: not system DMA channel 3 or 4
  (`dma_cdrom_or_spu_channel_active_during_confirmed_voice_line()` →
  `False`), not any of the SPU's 24 regular voices
  (`all_spu_voices_muted_dialogue_still_audible()` → `True`). The
  leading interpretation is that CD-ROM audio output connects to the
  SPU's CD Input as a direct hardware bus, distinct from the
  general-purpose DMA controller — a real PS1 architectural pattern
  (DMA channel 3 moves *sector data* into RAM for asset loading, a
  different signal path from the CD-ROM's own audio output). This
  project has not independently re-verified that specific hardware
  claim beyond what the DMA observation itself rules out, so it is
  recorded as the leading interpretation of solid negative evidence,
  not a proven mechanism.
- `classify_stream_format()` → `StreamFormat.UNKNOWN` — XA-ADPCM
  remains the only realistic candidate by elimination (CD-DA is
  structurally impossible on this disc), but the actual encoding was
  never independently observed.

## Stream format

`UNKNOWN` (see above). Genuinely still open.

## XAPACK linkage

No new causal link proven this pass — the DMA silence means there is
no runtime transfer event to correlate against the resolved LBA.

## Event boundaries

No improvement this pass.

## Extraction readiness

Unchanged: `NOT_READY` (per `gcrts.audio_event_extraction`) — source,
transport, and format are not all sufficiently known yet (transport is
now reasonably understood; format is not).

## Runtime integration

None added this pass — every finding here is investigation-tooling and
static-evidence-record level, not yet a proven, structured field
suitable for `RuntimeSnapshot`.

## Tests

**612 passed** (602 baseline + 10 new in `test_spu_audio_path.py`, now
43 total in that file), no regressions.

## Remaining blocker

There is no way to inspect the PS1 SPU's internal 512KB RAM directly
through this project's current tooling, which blocks verifying whether
any decoded-audio buffer exists there at all.

## Next milestone

Find a way to inspect SPU-internal RAM content (not just the
MMIO-mapped control registers) during a confirmed voice line, to check
directly for a decoded-sample buffer rather than continuing to infer
transport from its absence in system DMA.
