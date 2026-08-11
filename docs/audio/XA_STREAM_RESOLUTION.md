# XA File Open / Stream Resolution

Follow-up to `AUDIO_CONTEXT_RESOLUTION.md`, which fully closed "which
XAPACK file" (selector → table1 → table2 → literal filename string,
cross-validated against the real disc). This document picks up the next
question the milestone brief posed: how does the resolved filename
become an actual CD/XA stream, and can a real event's boundaries be
isolated? New module: `gcrts/audio_stream_source.py`.

## Headline result

**A real, live, doubly-confirmed "event start LBA" field was found** in
a structure this project had partially seen before (Stage C's own
earlier trace named `0x800A61A8` as "a structure pointer," never fully
decoded). Reading it now: `0x800A61A8` → `0x800A60EC`, and the structure
there has a field at offset `+0x04` that matched the real disc catalog's
own file-start LBA **exactly**, for two different resolved files
(`XAPACK06.BIN` → 116010; `XAPACK08.BIN` → 126218) — not approximately,
to the sector.

**The actual file-open call itself remains untraced — a genuine,
honestly-reported blocker**, not filled in with inference (see below).

## What was found: the constructed path string

Tracing forward from the resolved filename string
(`AUDIO_CONTEXT_RESOLUTION.md`'s table2 pointer), `0x80075c88` (already
called from `0x80075b68`) builds a small structure at the FIXED runtime
address `0x800A5F54`. Reading it live produced the complete, real
ISO9660 path string:

```
"\DAT\XA1\XAPACK09.BIN;1"
```

— including the standard PS1 CD-ROM `;1` version suffix. This is a
THIRD independent confirmation of the resolved filename (the first two
being the table lookup itself and the completely separate LBA-position
resolver from `AUDIO_CUE_RESOLUTION.md`), read directly from the exact
bytes a real file-open call would need.

## What was NOT found: the file-open consumer (genuine blocker)

Two systematic searches for whatever reads FROM `0x800A5F54` came up
empty:

1. **Absolute-address construction scan.** Every `lui`+`ori`/`addiu`
   pair across ~576KB of loaded code (`0x80000000`–`0x80090000`,
   covering every previously-traced sound-system address with wide
   margin) was checked for a second construction of the exact address
   `0x800A5F54`. Zero hits besides the one already-known writer.
2. **`$gp`-relative small-data scan.** PSY-Q-compiled code commonly
   accesses small/global data via a fixed offset from `$gp` rather than
   reconstructing an absolute address each time — this would be
   completely invisible to search #1. `$gp` was read live
   (`0x800A3BE0`), giving a target offset of `0x2374` (well within the
   standard ±32KB small-data window). A scan for `lw`/`sw`/`lh`/`sh`/
   `lb`/`sb` instructions using `$gp` as the base register with exactly
   this offset, across the same code range: zero hits.

Both are real, systematic techniques already proven elsewhere in this
project (the same absolute-address technique found the DMA-kickoff
function and MDEC address construction in earlier milestones); neither
found a consumer here. **Per this project's own standing rule, this gap
is reported honestly rather than filled with expected-PS1-behavior
inference.** The most likely explanation is an addressing scheme
outside what these two techniques search for (e.g. a pointer cached in
a register-resident or heap structure, set up once elsewhere, rather
than re-derived from a constant on each access) — or the consumer
simply wasn't resident in this session's live RAM window (overlay
drift, already well-documented elsewhere in this project, is a live
possibility).

Confirmed via polling (20 samples, 1.5s apart, spanning the STARTING
state): the `0x800A5F54` structure itself never changes after its
initial write — it is a write-once buffer for the path string, not an
accumulating stream-state structure. Whatever consumes it does so
without writing anything back to this same address.

## What was found instead: a real event-boundary structure

`0x800A61A8` → `0x800A60EC` (24+ bytes), fields confirmed live:

| Offset | Content (live samples) | Status |
|---|---|---|
| `+0x00` | last-requested raw params (duplicate of `0x800A6114`) | Confirmed, matches known field |
| `+0x04` | **116010 / 126218** — exact match to the real disc file's own start LBA, twice | **CONFIRMED** |
| `+0x08` | 120310 / 129542 — static per-context (not a live counter, confirmed by polling) | Observed, plausible "event end LBA", NOT independently confirmed |
| `+0x0C` | identical to `+0x04` in every sample | Confirmed to duplicate `+0x04` |
| `+0x10` | identical to `+0x08` in every sample | Confirmed to duplicate `+0x08` |
| `+0x14` | 131841 — **identical across two different resolved files** | Observed; NOT file-specific, role unclear |

`gcrts.audio_stream_source.resolve_audio_stream_source` exposes exactly
this: `file_start_lba` (the confirmed field, cross-validated against
`gcrts.xa_disc_index` — `LIVE_VERIFIED` only when it matches a real
file's exact start) plus the two unconfirmed fields, honestly labeled
and never upgraded to a claimed meaning they don't have evidence for.
Deliberately does NOT introduce field names like `event_end_lba` for
`+0x08` — that would imply a confidence this investigation doesn't have.

## Triple cross-validation

Live-verified: `event.source_file` (position-based resolver),
`audio_context.resolved_disc_path` (selector-table resolver), and
`audio_stream_source.matched_disc_path` (this structure) all agreed
exactly (`DAT/XA1/XAPACK08.BIN`) on the same real capture. Three
genuinely independent mechanisms, zero shared code paths, one answer.

## Channel resolution — unchanged, still open

No new evidence on true XA channel/filter selection was found this
pass. `xa_channel` remains only positionally-inferred
(`AUDIO_CUE_RESOLUTION.md`'s Observation 4: `channel = (lba -
file_start) % 8`, a confirmed artifact of the disc's own interleaving,
not proven to reflect the SPU's actual channel selection). Nothing in
the newly-found structures (`0x800A5F54`, `0x800A60EC`) contains an
obviously channel-shaped field.

## Event boundaries / extraction feasibility

**Not yet reliable.** `file_start_lba` is solid; a genuine "event end"
boundary is only a plausible, unconfirmed candidate (`+0x08`); true
channel selection is unconfirmed. Isolating one event's exact physical
XA sectors would need at least the channel question resolved — not
attempted this pass, honestly incomplete rather than approximated.

## Runtime integration

`RuntimeVisualProvider.last_audio_stream_source` (same caching pattern
as the other `last_*` attributes, computed every `scan()` regardless of
whether an audio event is currently active — the descriptor pointer is
a fixed global, so a stale read is itself informative).
`RuntimeSnapshot.active_audio` entries carry a nested `"stream_source"`
field. The Visual Inspector's audio panel shows the confirmed start LBA
and matched disc path, or `UNKNOWN` when unconfirmed.

## Tests

13 new tests: 7 in `tests/test_audio_stream_source.py` (including direct
regressions of both live-confirmed samples and a check that unconfirmed
fields are never silently upgraded to a claimed meaning), 6 in
`tests/test_xa_disc_index.py` for the new `resolve_filename_to_path`
real-disc cross-check this pass also added (a genuine bug fix:
`gcrts.audio_context` previously hard-capped resolution at file number
8, causing a real, valid selector resolving to `XAPACK09` to be wrongly
reported as unresolved — caught live this session, not by a test).

## Last confirmed node / next unresolved node (per the milestone's own required format)

- **Last confirmed node**: `0x800A61A8` → `0x800A60EC+0x04`, a real,
  live, disc-cross-validated file-start LBA, independent of and in
  agreement with both prior resolution mechanisms.
- **Next unresolved node**: whatever reads the constructed path string
  at `0x800A5F54` to perform the actual file-open, and whatever selects
  the true XA channel/filter.
- **Why blocked**: two systematic static-search techniques (absolute
  address construction, `$gp`-relative access) both found zero
  consumers across ~576KB of loaded code.
- **Best next experiment**: search for the consumer via data-flow from
  a DIFFERENT angle — e.g. look for what writes/reads
  `0x800A60EC+0x08` (the unconfirmed "event end" candidate) specifically,
  since it's more likely to be touched by channel/playback-control logic
  than the path-string buffer is; or attempt to locate the true channel
  selector by searching for writes to the CD-ROM controller's own
  filter-register-adjacent RAM shadow state, if one exists and is
  identifiable, following the same pattern that found `0x800a6106`-family
  addresses in earlier Stage C work.

## Follow-up milestone (XA Channel / Filter Runtime Resolution): the CD-ROM driver itself, found

The "best next experiment" above was pursued directly: rather than a
third static scan for the filename-string consumer, this pass followed
the milestone brief's own suggestion and went looking for CD-ROM
filter/channel runtime state instead. New module:
`gcrts/cdrom_driver_map.py`.

### What was found, live and hardware-exact

A **hardware write watchpoint** (GDB `Z2` packets, not a static scan) on
the CD-ROM controller's MMIO block (`0x1F801800`-`0x1F801803`) caught 5
real writes within seconds, all from PCs inside this project's own
already-scanned RAM code range (`0x8008xxxx`) — disproving an initial
hypothesis that this delegates invisibly to BIOS ROM. Reading the small
pointer-variable table those writes actually go through gave an EXACT,
byte-for-byte match to the real PS1 CD-ROM hardware register map:

| RAM variable | Live value | Real hardware register |
|---|---|---|
| `0x800A30BC` | `0x1F801800` | Index/Status |
| `0x800A30C0` | `0x1F801801` | Command / Response FIFO |
| `0x800A30C4` | `0x1F801802` | Parameter FIFO / Data |
| `0x800A30C8` | `0x1F801803` | Request / IRQ enable-ack |

This is a genuine architectural finding, not specific to this one
address: it explains why the filename-consumer scans (this doc's own
earlier section, above) and a fresh MMIO-address-construction scan run
this pass all came back with zero hits — the real addressing scheme is
"load a pointer once from a small RAM variable, reuse it across many
accesses," which no `lui`+`ori`/`addiu`-adjacency scan can ever see.
`gcrts.cdrom_driver_map.resolve_cdrom_driver_map` exposes exactly this
check, live-verified end-to-end through
`RuntimeVisualProvider.last_cdrom_driver_map` this session.

**The shared "issue one CD-ROM command" routine was located**,
`0x80081C00`-`0x80081C54`: sets index=3, then writes a command byte and
up to 3 parameter bytes (read from the caller's own stack frame)
directly to the confirmed hardware ports — exactly the real CD-ROM
command protocol shape. `SETFILTER_COMMAND = 0x0D` ("Sets XA audio
filter", 2 params: file number, channel number) is cross-checked against
public documentation (psx-spx, LibPSn00b Runtime Library Reference), not
derived from guesswork.

**A parallel dead end, ruled out rather than left ambiguous**: the
sound-dispatch cluster's `0x800A61B0` field (previously just "a
pointer... not identified yet" per Stage C) is confirmed to be a real
**BIOS event descriptor** returned by `OpenEvent` (public PS1 kernel
docs: event descriptors are `F1000000h`+, matching the live value read
this session, `0xF1000001`, exactly). `0x80077864`/`0x8007789c` are
BIOS `EnableEvent`/`DisableEvent` calls (B0h function `0x0C`/`0x0D`,
confirmed via the same public sources) on that descriptor — real,
confirmed, but not the channel/filter mechanism. Their third-branch
sibling, `0x80077d78` (initially promising: a per-index 16-byte-stride
table write), decodes to PS1 Root Counter (Timer 0/1/2) mode/target
register setup, not CD/XA anything — a real negative result, reported
rather than silently dropped.

### What was NOT caught live (genuine blocker, unchanged in kind)

Three live-breakpoint attempts at the confirmed command-issuing
routine's entry (`0x80081C00`) — one for 90s, one armed immediately
after a fresh state reload, one for 75 continuous seconds — produced
**zero hits**, despite confirmed ongoing CD-ROM interrupt activity in
the same window (the MMIO watchpoint caught 5 writes within seconds of
arming). Most likely explanation: every available save state lands
either mid-way through an already-established `ReadN` stream (which
delivers via interrupts with no command reissue) or in a between-lines
idle moment issuing no new commands at all — catching the actual
Setfilter call needs either input injection to force a fresh dialogue
advance, or a save state landing in the exact single-frame dispatch
window, neither available this session. **The live command byte and
file/channel parameter values for one real Setfilter call remain
unconfirmed.** `xa_channel` stays exactly as unconfirmed/positional as
`AUDIO_CUE_RESOLUTION.md` originally found it — this pass strengthens
*why* (the real command protocol and register map are now known) without
yet closing the live-value gap.

### Runtime integration

`RuntimeVisualProvider.last_cdrom_driver_map`, `RuntimeSnapshot.cdrom_driver`
(top-level, not per-event — the driver's own register map is a static
code-level fact, not something that changes per audio event), and a new
Visual Inspector panel line ("CD-ROM driver: LIVE_VERIFIED..." or
"UNKNOWN").

### Tests

5 new tests in `tests/test_cdrom_driver_map.py`.

## Follow-up (Capture the Real CD-XA Setfilter Command): the live value, finally caught

The gap this whole document left open — a real, live Setfilter call with
its actual file/channel parameter values — is now closed. New module:
`gcrts/cdrom_setfilter.py`.

### The bug in the original approach, found and fixed

Three live-capture sessions (spanning ~200 real seconds, including two
full voiced segments actually playing) caught the breakpointed routine
firing repeatedly, but ONLY with command byte `0x00` (Sync), always
from one fixed caller (`ra=0x80081bd4`). This looked like a genuine
negative result — until a **static scan** for every real command-write
call site (searching the full ~576KB loaded-code range for "load the
command-register pointer, then `sb` into it") found exactly 3 sites,
none of which was the address the earlier captures had used. The
original capture had been reading the command byte from the wrong
stack offset (`sp+0x11`, a leftover/unrelated byte) instead of the real
one (`sp+0x12`, six instructions later) — an off-by-one that happened
to still return a plausible-looking byte (`0x00`) every time, silently
masking the mistake across three separate live sessions. This is
recorded here deliberately, not smoothed over: a plausible wrong answer
that never crashed or looked obviously broken is exactly the kind of
error this project's own standing discipline (verify live, don't trust
one signal) exists to catch — and did, eventually, once genuinely new
evidence (the static scan) was brought in rather than repeating the
same live-capture technique a fourth time.

### The real, live, reproduced values

Software breakpoints at all 3 real call sites, reading `$v0` (proven,
not guessed, to already hold the exact command byte at each site) on
every hit, immediately showed real, varied command traffic — unlike the
flat all-Sync result before. Within seconds, a genuine Setfilter
(`0x0D`) fired at `0x8008182C`:

```
a0=0x00000002   (parameter count -- matches Setfilter's real 2-parameter protocol exactly)
a1=0x800A3070   (pointer to the parameter buffer)
buffer contents: [2, 1, 0, 0, ...]   (each parameter as a 4-byte-aligned word)
```

**Reproduced byte-identical on a second, fully independent capture**
(fresh state reload, fresh connection, same result) — not a one-off.
Under Setfilter's standard documented parameter order (file, channel):
**file=2, channel=1**. `file=2` is cross-validated against the real
disc catalog (`gcrts.xa_disc_index.resolve_filename_to_path("XAPACK02")`
→ `DAT/XA1/XAPACK02.BIN`, a real file) — not a guess.

**Honest limit on this evidence**: the capture script that caught this
didn't also read the live position counter/LBA at the exact same
instant, so `file=2` isn't triple-cross-validated the way the
selector-table chain in `AUDIO_CONTEXT_RESOLUTION.md` is. The
confidence label (`LIVE_CAPTURED`) covers the raw register/memory
evidence, which is solid and reproduced; the file/channel semantic
labeling rests on the standard documented Setfilter parameter order,
not an independent same-instant position check.

### Why this required abandoning "just poll" for this one case

Every other resolver in this project's audio-tracking stack works by
polling fixed RAM addresses — no breakpoints, by design, because this
project's own history includes real breakpoint/continue hangs.
Setfilter is a one-shot event with no persistent, pollable field
anywhere in RAM holding "the last real Setfilter's parameters" (this
investigation looked; the closest candidate, the command staging byte
at `0x800A30D4`, gets overwritten by every subsequent command within
milliseconds). Catching it genuinely required a live breakpoint
session — several of them, plus a static scan to fix the first
session's own mistake. `gcrts.cdrom_setfilter` therefore does not
provide a `capture_setfilter_live(read_memory)` polling function; it
documents the confirmed, reproduced facts as a historical record,
exactly the pattern `gcrts.runtime_audio.KNOWN_CUE_SOURCES` already
established for a real one-time observation with no general
live-polling path.

### Runtime integration

`RuntimeSnapshot.last_known_setfilter` (top-level, historical — not
re-derived per scan) and a Visual Inspector panel line ("Last known
Setfilter (historical): file=2 channel=1 [LIVE_CAPTURED]").

### Tests

9 new tests in `tests/test_cdrom_setfilter.py`.

### Important follow-up correction (Audio Event Isolation milestone)

A later live re-check found this Setfilter call is **not proven to be
event-specific** — two independent simultaneous cross-checks (position
counter + playback state read at the exact same instant as the hit)
both found it firing during a STOPPED state with stale, unrelated
`last_req_params`, never during an active PLAYING dispatch. It's most
likely a fixed default/reset value, not a per-cue channel selection.
See `AUDIO_EVENT_EXTRACTION.md` for the full account and
`gcrts.cdrom_setfilter.is_proven_event_specific()` (returns `False`,
with the evidence attached). The raw register/memory evidence
(`file=2, channel=1`, the real command protocol, the real hardware
register map) remains real and reproduced — only the "this is what a
specific playing event selects" interpretation is retracted.

### Third follow-up (Per-Event XA Channel Capture): the "one cue, one Setfilter" model is wrong — it looks persistent instead

A ~460-second live capture on the CURRENT (not reloaded) game state,
spanning a real, user-confirmed audible playback, found the same
`params=(2, 1)` on all 8 Setfilter hits observed, while the position
counter visited 5 different disc-seek targets in that same window. The
filter never tracked the seek target. See `CDROM_SETFILTER_CAPTURE.md`
for the full transcript and `gcrts.cdrom_setfilter.filter_appears_persistent()`
(`True`). Separately, and just as importantly: the audio state byte
(`0x800A6107`) never transitioned to PLAYING during this entire window
despite confirmed real audio — an honest caveat now recorded in
`gcrts.runtime_audio`'s own module docstring.
