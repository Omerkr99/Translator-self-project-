# Secondary CD-ROM Driver Discovery

Goal: find the hidden CD-ROM command path that actually starts
XA-ADPCM playback.

## Headline result

**Found real, additional CD-ROM register pointer sets — but they turn
out to be part of a generic interrupt/DMA dispatch table, not a
dedicated second audio driver.** New module:
`gcrts/cdrom_driver_discovery.py`.

## Known driver

Already ruled out as the audible-XA path (`XA_PLAYBACK_PATH.md`): the
one pointer set at `0x800A30BC`-`0x800A30C8`, its 3 command-write
sites, and the repeating `Setloc/Setmode(0x01)/ReadN/Pause/Setfilter`
cycle.

## Additional MMIO pointer sets

A different search technique than any tried before — scanning the
*entire* 2MB live RAM image for the raw 4-byte values
`0x1F801800`/`01`/`02`/`03`, rather than scanning code for a specific
address-construction pattern — found **7 additional complete
4-register sets** beyond the known one:

```
0x8001586C, 0x800158F0, 0x80015940, 0x80015950   (low-memory cluster)
0x800A3140, 0x800A3190, 0x800A31A0               (same page as the known set)
```

Each holds the 4 register addresses in the exact same relative order
and 4-byte spacing as the known set — not coincidence; real,
deliberately-laid-out data.

## Hardware writer families

**None of the new sets has a confirmed command-issuing writer.** A
targeted static scan (the same `lui`+`lw`+`sb` pattern that found the 3
known sites) against every new set's offsets found zero hits. This
doesn't mean nothing ever writes through them — only that this
project's one known code-search technique doesn't find a writer for
them, consistent with (not contradicting) `XA_PLAYBACK_PATH.md`'s own
finding that this pattern is exhausted.

## What the `0x800A31xx` cluster actually is

Direct inspection of `0x800A3100`-`0x800A3200` (the full surrounding
region) revealed its real structure: alongside the 3 CD-ROM register
sets, it holds real DMA channel address pairs for channels 1, 2, 3, and
5 (MDEC-out, GPU, CD-ROM, PIO — each `MADR`/`CHCR` pair at its correct,
standard offset from the real DMA base `0x1F801080`), `I_STAT`/`I_MASK`
(`0x1F801070`/`0x1F801074`), and a block of function-pointer-shaped
values in this game's own loaded code range. This is a **generic
interrupt/DMA dispatch configuration table** — GPU, MDEC, CD-ROM, and
PIO all represented together — not an isolated audio-specific
structure.

One real, direct link to the already-known audio system was found and
traced: code at `0x80081B10` passes `0x800A3108` (which itself holds
`0x800A30D4` — the already-confirmed command-staging byte address) to
a function (`0x80077F68`) alongside a format-string-shaped argument —
most consistent with a debug-log call annotating the known system with
a human-readable label, not a second functional command path.

## Overlay residency

Not separately re-verified this pass; the audio profile fingerprint
check earlier in this investigation series already confirmed the
loaded overlay stayed constant across every capture session so far.

## ReadS

Not observed again — no new capture attempt was made against these
newly-found (but writer-less) pointer sets, since no command-issuing
code was found to arm a breakpoint on.

## New playback path

Not found. This milestone's real contribution is narrowing what the
"missing" path is *not*: it is not hiding behind a second, parallel
CD-ROM command driver using a structurally identical pointer-set
pattern to the known one. The additional register references that do
exist serve a different, lower-level purpose (interrupt/DMA
descriptor table).

## XAPACK correlation

Not applicable — no new playback path was found to correlate against.

## Runtime integration

None added — no confirmed live signal exists yet to expose.

## Classification

Per this milestone's own required taxonomy
(`SAME_DRIVER_DIFFERENT_ENTRY` / `SECOND_DRIVER` / `OVERLAY_VARIANT`):
none fit cleanly. Recorded as its own, more precise category,
`HW_DISPATCH_TABLE_NOT_A_COMMAND_DRIVER`, backed by real evidence
(`gcrts.cdrom_driver_discovery.DISCOVERED_SETS`) rather than forced
into an inaccurate existing bucket.

## Tests

8 new tests in `tests/test_cdrom_driver_discovery.py`.

## Remaining blocker before Audio Inspector

The real XA-ADPCM-configuring code path is not reachable through either
of this project's two RAM-search strategies (code-pattern scanning or
raw-value scanning) applied against register addresses this project
already knows to look for.

## Next milestone

Given a raw RAM value scan just found real, previously-unknown data
this project's code-pattern scans missed entirely: apply the same
raw-value-scan technique to the SPU (Sound Processing Unit) register
range (`0x1F801C00`-`0x1F801FFF`) instead of the CD-ROM range — since
XA-ADPCM audio's actual destination is the SPU, not just the CD-ROM
controller, and this project has never yet searched for SPU register
references at all.
