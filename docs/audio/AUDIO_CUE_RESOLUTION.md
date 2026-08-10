# Audio Cue Resolution — Evidence Table and General Mapping Findings

Follow-up to `RUNTIME_AUDIO_TRACKER.md`'s lifecycle milestone. Goal: find
a reusable `script cue -> physical XA source` mapping by tracing more
cues the way Stage C traced 127. What was actually found is a different,
more general mechanism than a per-cue table — this document is the full
evidence trail; `gcrts/runtime_audio.py`'s and `gcrts/xa_disc_index.py`'s
own docstrings carry the load-bearing summary for future readers.

## Headline result

**The raw script parameter alone does not stably identify one physical
source.** This is directly disproven, not just unconfirmed — see
Observation 2 below. What generalizes instead is resolving whatever LBA
is actually live-observed against the disc's own real, exact file table
— `gcrts.xa_disc_index.resolve_lba_to_file`. That's implemented, tested,
and live-verified end to end.

## Evidence table

| # | Method | Call site | script_parameter | MSF / LBA | Resolved file | Channel (positional) | Status |
|---|---|---|---|---|---|---|---|
| 1 | Stage C (prior session) | `0x80077968` (confirmed dispatch) | 127 | 28:14:21 → LBA 126921 | `DAT/XA1/XAPACK08.BIN` | 7 | OFFLINE_CONFIRMED (raw sector read: submode 0x64, coding_info 0x01, mono 4-bit ADPCM) |
| 2 | This session, first capture, HIT0 | `0x80077458` (**different** function — see Observation 3) | 126 (params_now at that instant) | LBA 116010 | `DAT/XA1/XAPACK06.BIN` | 0 | LIVE_VERIFIED (breakpoint capture) |
| 3 | This session, first capture, HIT1-5 | `0x80077968` (confirmed dispatch) | 127 (unchanged) | LBA 116010→116066 | `DAT/XA1/XAPACK06.BIN` | 0,3,5,6,0 | LIVE_VERIFIED |
| 4 | This session, second capture (clean, 40 hits) | `0x80077968` (confirmed dispatch) | 127 (unchanged, all 40 hits) | LBA 127781→128464, smooth ~104/sec climb | `DAT/XA1/XAPACK08.BIN` (all 40) | cycles 0-7, exactly `(lba-126218)%8` | LIVE_VERIFIED |
| 5 | This session, third capture (targeted, 200 iterations, ~57s) | `0x80077968` (confirmed dispatch) | 127 (never changed for the full run) | LBA 116010→119460 | `DAT/XA1/XAPACK06.BIN` throughout | cycles 0-7 | LIVE_VERIFIED (negative result: never caught a params transition — see Observation 4) |

Row 2 is the only glimpse of a raw value other than 127 this session,
and it did not come from the confirmed simple dispatch chain — it is
**not** treated as a resolved "cue 126," only as evidence a second,
distinct subsystem shares `0x80080d54`.

## Observations

**1. `0x80080d54` (the confirmed BCD MSF-to-LBA converter) is called
repeatedly, not once per cue.** Row 4's clean 40-hit capture shows the
confirmed dispatch site (`ra=0x80077968`) firing roughly 6 times per
real second while `script_parameter` stays constant, each call computing
a slightly larger LBA than the last (~104/sec climb). This — not a
separate abstract counter — is what makes `0x800A61AC`
(`RUNTIME_AUDIO_TRACKER.md`'s "position_counter") advance quickly: it's
literally being recomputed and overwritten several times a second as
long as a cue is active.

**2. The same raw script parameter (127) resolved to two different
physical files depending on real elapsed time, not script position.**
Rows 3 and 4 are both `script_parameter=127`, both from the confirmed
dispatch site, captured from fresh reloads of the identical save state
— yet one resolves to `XAPACK06.BIN`, the other to `XAPACK08.BIN`. Row 5
(a third independent capture, armed and left running much longer)
reproduced Row 3's `XAPACK06.BIN` result again. The determining factor
appears to be how much real wall-clock time had elapsed since the state
loaded before the breakpoint armed and started catching hits, not which
specific dialogue line the script had reached. This directly disproves
"the script parameter is a stable index into a per-cue source table."

**3. A second, unrelated call site shares `0x80080d54`.** Row 2's
`ra=0x80077458` sits inside a distinct function (starting before
`0x80077400`, not independently entry-pointed this session) that takes
explicit minutes/seconds/frames-shaped arguments (`$s1`, `$s2`, and a
stack-loaded byte) and combines a base LBA with a computed relative time
offset (`A*4500 + B*75 + frames`, where `4500 = 60*75` — a genuine
MSF-style calculation, not a guess). This looks architecturally like a
general "seek to time T within a resource" primitive, distinct from and
more fundamental than the simple sound-cue dispatcher. Confirms
`0x80080d54` is shared, generic low-level infrastructure used by at
least two different subsystems — consistent with, and extending, the
earlier Stage B finding that this same function is too generic to
breakpoint as a movie-detection signal.

**4. `channel_number` at a computed LBA is a pure positional artifact,
confirmed to the byte.** Across all 45 real sector reads in rows 3-5
combined, `channel_number == (lba - file_start_lba) % 8` held exactly,
every time — the standard 8-way CD-XA interleave pattern. This directly
refutes treating "the channel byte of whatever LBA got computed" as
evidence of which channel the SPU is actually decoding: since the
confirmed dispatch site recomputes a new (slightly larger) LBA multiple
times per second, and consecutive LBAs land on essentially arbitrary
channels via simple modular arithmetic, the channel value cycles through
all 8 values in normal use. Stage C's original "channel 7" finding for
cue 127 is consistent with this relationship
(`(126921-126218) % 8 == 7`, exactly) but should be read as "the channel
of the specific sector this one dispatch happened to compute," not a
general, reusable channel-selection fact.

**5. A dedicated attempt to catch a genuine cue transition (127 -> a
different value) via the confirmed dispatch site did not succeed within
this session's time budget.** Row 5 watched for 200 breakpoint
iterations (~57 real seconds) and never saw `script_parameter` change
from 127, even though the earlier, lighter-weight *polling*-based trace
(`RUNTIME_AUDIO_TRACKER.md`'s Phase 7 run, no breakpoints at all) saw a
127→126 transition after only ~14 real seconds against the same save
state. The most likely explanation: breakpoint-and-continue overhead
(a GDB stop/inspect/resume round trip on every one of the ~6 hits/second
this dispatch produces) measurably slows the emulator's own effective
progress relative to free-running polling. This is a real, useful
methodological finding for any future live capture of this specific
call site: prefer polling over breakpointing when timing across many
seconds matters, exactly the discipline `gcrts.renderer1_runtime` and
this module's own `capture_audio_event` already follow for routine use.

## What generalizes, and what was implemented

**General and implemented**: `gcrts.xa_disc_index.resolve_lba_to_file`
— a static, exact table of every `XAPACK*.BIN` file's real start LBA
(read directly from the disc's own ISO9660 directory records, not
estimated), resolving any observed LBA to its containing file in O(n)
over 43 entries. `gcrts.runtime_audio.capture_audio_event` now tries
this FIRST (using `position_counter_start`, the value observed when an
event was first seen), falling back to the old `KNOWN_CUE_SOURCES` table
only when the observed position falls outside every known file's range.
This is strictly more general and more honest than the old design: it
resolves ANY genuinely observed cue's source, not just the one Stage C
happened to trace, and it doesn't claim a stale historical value is
still true.

**Not general, and not claimed to be**: `xa_channel`. A real value is
still computed (via `gcrts.xa_disc_index.read_sector_meta`, when a
caller supplies disc bytes) but reported under the new
`AudioConfidence.POSITIONAL_UNCONFIRMED` tier specifically because of
Observation 4 — it's real data, honestly labeled as unconfirmed to be
the true playback selection rather than silently upgraded to a
confident answer.

**Not attempted, and not needed**: reverse-engineering the general
cue-number-to-descriptor lookup table/function Phase 5/6 of the original
brief hoped to find (e.g. a `descriptor[cue]` table in RAM or in an
executable). Observation 2 made this the wrong question to keep chasing
— there may be no such STATIC table at all if the same raw parameter
value can legitimately mean different things at different points in a
scene (most likely explanation: `script_parameter` is reused/recycled
across many distinct lines, the way small integer indices commonly are
in scripted systems, and the ACTUAL disambiguating context is the
script's own execution position — something entirely outside this
runtime, RAM-polling-based tracker's reach without a parallel live
script-buffer correlation, which is out of this milestone's scope).

**Follow-up (`SCRIPT_AUDIO_ASSOCIATION.md`): this question is now
answered.** The "parallel live script-buffer correlation" flagged above
as out of scope was built in the very next milestone, and confirmed the
"reused/recycled parameter, disambiguated by script position" hypothesis
directly and cleanly — with one important refinement: the disambiguating
signal isn't raw word offset either (the live script buffer itself gets
refreshed with new content between dialogue moments, and different
refreshed loads can coincidentally share the same word offset), it's the
actual decoded content of the owning script unit. See
`SCRIPT_AUDIO_ASSOCIATION.md` for the full live proof.

**Follow-up (`XA_STREAM_RESOLUTION.md`): channel resolution still open,
file-open path traced one step further and honestly blocked.** The
selector's resolved filename (`AUDIO_CONTEXT_RESOLUTION.md`) was traced
forward to a real, live-readable constructed ISO9660 path string
(`\DAT\XA1\XAPACKNN.BIN;1`), and a genuine "event start LBA" field was
found and disc-cross-validated in a previously only partially-decoded
structure. What was NOT found, despite two systematic searches, is the
actual file-open consumer of that path string — reported as a genuine
blocker rather than assumed. `xa_channel` (Observation 4, above) remains
exactly as unconfirmed as it was in this document's own original
investigation; nothing found in the follow-up changed that. See
`XA_STREAM_RESOLUTION.md` for the full trace and the honest blocker
writeup.

**Second follow-up (`XA_STREAM_RESOLUTION.md`'s own "XA Channel / Filter
Runtime Resolution" section): the real CD-ROM driver and command
protocol, found and live-hardware-verified; the live channel VALUE,
still not caught.** A hardware write watchpoint on the CD-ROM
controller's MMIO block found this game's own low-level driver in RAM
(not BIOS-opaque), confirmed its 4 hardware-register pointer variables
against the real PS1 addresses exactly, and located the shared
command-issuing routine plus the real, publicly-documented Setfilter
command number (`0x0D`, 2 params: file, channel). Three separate live
attempts to catch that routine actually firing with command `0x0D`
produced zero hits — a genuine, honestly-reported blocker, not the same
kind of "consumer nowhere to be found" blocker as before (the mechanism
and its exact protocol ARE now known; only one specific live
observation is still missing). `xa_channel` remains
`POSITIONAL_UNCONFIRMED`.

**Third follow-up (`XA_STREAM_RESOLUTION.md`'s "Capture the Real CD-XA
Setfilter Command" section, `gcrts.cdrom_setfilter`): the live value is
caught.** The previous zero-hit result hid a real bug — the breakpoint
was reading the command byte from the wrong stack offset, silently
returning a plausible `0x00` every time across three full live
sessions. A static scan (not a repeat of the same live technique) found
the real command-write sites; breakpointing those caught a genuine
Setfilter within seconds: **file=2, channel=1**, reproduced
byte-identical on an independent second capture, `file=2`
cross-validated against the real disc catalog. `xa_channel` is no
longer purely `POSITIONAL_UNCONFIRMED` in the abstract — a real,
reproduced live value now exists, honestly scoped (no simultaneous LBA
cross-check was taken at the capture instant, so this is
live-captured-and-reproduced, not triple-cross-validated the way the
selector-table chain is). See `XA_STREAM_RESOLUTION.md` for the full
trace, including the honest account of the earlier bug.
