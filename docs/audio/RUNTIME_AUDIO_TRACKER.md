# Runtime Audio Tracker

Milestone goal: prove `START -> PLAYING -> current offset -> STOP` for a
real voice cue, live, and make that available through `RuntimeSnapshot` --
closing the "playback lifetime" gap `CURRENT_SYSTEM_STATUS.md` flagged as
open after Stage C's script-cue-to-disc-sector trace. New module:
`gcrts/runtime_audio.py`. Wired into `gcrts/runtime_visual_provider.py`
(`RuntimeVisualProvider._audio_event`, cached on
`provider.last_audio_event`, same pattern as `last_renderer1_validation`)
and `gcrts/runtime_snapshot.py` (`active_audio` is no longer an always-
empty placeholder). A minimal read-only panel was added to
`gcrts/visual_inspector_ui.py`. 25 new tests
(`tests/test_runtime_audio.py`, `tests/test_runtime_snapshot.py`'s new
audio section); full suite **425 passed** (400 + 25), no regressions.

**Follow-up milestone (Audio Cue Resolution Generalization,
`AUDIO_CUE_RESOLUTION.md`)**: the source-resolution half of this
document (originally: a small `KNOWN_CUE_SOURCES` table keyed by raw
script parameter) has been superseded by a more general, live mechanism
-- resolving `source_file` from whatever LBA is actually observed
(`gcrts.xa_disc_index.resolve_lba_to_file`, an exact table built from
the disc's own file records) rather than a per-cue lookup. This was a
necessary correction, not just an enhancement: the same raw script
parameter was live-observed resolving to two different physical files
at different times, disproving the original table's implicit assumption
that a script parameter is a stable source identifier. See
`AUDIO_CUE_RESOLUTION.md` for the full evidence and
`gcrts/runtime_audio.py`'s module docstring for the current, correct
summary. `KNOWN_CUE_SOURCES` is retained only as a documented,
last-resort fallback. Test count: **438 passed** (425 + 13: 10 in
`tests/test_xa_disc_index.py`, net +3 in `tests/test_runtime_audio.py`).

**Second follow-up milestone (Script Context <-> Audio Dispatch
Correlation, `SCRIPT_AUDIO_ASSOCIATION.md`)**: answers the question
`AUDIO_CUE_RESOLUTION.md` left open -- why the same raw parameter
resolves to different files. New module
`gcrts/script_audio_association.py` correlates the live script cursor
(`0x800A4CEA`, already confirmed by a prior session's
`DECODER_READ_CURSOR.md`) and decoded script buffer against each live
`RuntimeAudioEvent`, live-proving across 4 real samples that a
content-based fingerprint of the owning `ScriptUnit` -- not word offset,
not the raw parameter -- correlates exactly with which physical file
gets used. Wired into `RuntimeVisualProvider.last_script_association`
and `RuntimeSnapshot.active_audio`'s new nested `"script_context"`
field. Test count: **452 passed** (438 + 14).

**Third follow-up milestone (Audio Context Resolution +
Audio Captions, `AUDIO_CONTEXT_RESOLUTION.md` + `AUDIO_CAPTIONS.md`)**:
found the actual causal mechanism -- the "127" inline parameter every
prior pass tracked was never the real per-line selector; the
`sound_or_voice_cue` control WORD's own low byte is, live-confirmed and
traced through a real 2-level table dispatch (`gcrts/audio_context.py`).
Also added a semantic "what is being heard" layer
(`gcrts/audio_caption.py`) kept strictly separate from source/context
identity, honestly limited to real dialogue text as its only
self-produced caption source (no audio listening capability exists in
this environment -- no SFX/ambient descriptions are fabricated). Both
wired into `RuntimeVisualProvider`/`RuntimeSnapshot`'s new
`"audio_context"`/`"caption"` fields and the Visual Inspector panel.

**Fourth follow-up milestone (Handler -> Physical Source Resolution,
also folded into `AUDIO_CONTEXT_RESOLUTION.md`)**: closed the one gap
the third milestone had explicitly left open. What looked like a
2-level dispatch to "two different handler functions" turned out, on
full disassembly, to be a 2-level lookup into a literal, static, embedded
filename string table -- there was no handler function to trace into.
`table1`'s byte is the XAPACK file number directly. Initially validated
for only 9 entries (0-8); a follow-up live check (Phase 5, below) found
the real table actually spans the disc's full 43 files (00-42), catching
and fixing a real bug where a valid selector resolving to file 9 was
wrongly reported as unresolved. Live-validated for real selectors 25,
26, and 28, cross-checked against the completely independent
LBA-position-based resolver via `cross_validate_source()` -- all agree
exactly. Test count: **478 passed** (452 + 26).

**Fifth follow-up milestone (XA File Open / Stream Resolution,
`XA_STREAM_RESOLUTION.md`)**: traced past the resolved filename toward
the actual file-open call. Found the filename gets built into a real,
live-readable ISO9660 path string (`"\DAT\XA1\XAPACK09.BIN;1"`, complete
with the standard `;1` version suffix) at a fixed address -- a THIRD
independent confirmation of the resolved file. The actual file-open
consumer itself is a genuine, honestly-reported blocker: two systematic
searches (absolute address construction, `$gp`-relative small-data
access) both found zero consumers across ~576KB of loaded code. Separately,
found and confirmed a real "event start LBA" field in an adjacent
structure (`0x800A61A8` -> `0x800A60EC+0x04`), matching the real disc
catalog exactly for two different files -- genuine progress on event
boundaries despite the file-open blocker. All three independent
resolution mechanisms (position-based, selector-table-based,
descriptor-structure-based) now cross-validate exactly on live capture.
Also fixed the real bug this pass's own investigation surfaced in
`gcrts.audio_context` (the too-narrow 0-8 cap). Test count: **492
passed** (478 + 14: 7 in `test_audio_stream_source.py`, 6 in
`test_xa_disc_index.py`'s new `resolve_filename_to_path` coverage, net
+1 elsewhere).

**Sixth follow-up milestone (XA Channel / Filter Runtime Resolution,
`XA_STREAM_RESOLUTION.md`'s own follow-up section, `gcrts.cdrom_driver_map`)**:
pursued the file-open blocker from a different angle -- CD-ROM
filter/channel runtime state instead of a third filename-consumer scan.
A live hardware write watchpoint on the CD-ROM controller's MMIO block
(`0x1F801800`-`0x1F801803`) caught real writes from this game's own RAM
code within seconds, and reading the pointer-variable table those writes
go through gave an exact, byte-for-byte match to the real PS1 CD-ROM
hardware register map (`0x800A30BC`/`C0`/`C4`/`C8` -> the 4 real
registers) -- explaining, architecturally, why the earlier
filename-consumer scans found nothing (this game's addressing style
loads a pointer once from a small RAM variable rather than constructing
addresses inline, invisible to an adjacency scan). The shared "issue one
CD-ROM command" routine was located (`0x80081C00`), and the real,
publicly-documented Setfilter command number (`0x0D`, LibPSn00b/psx-spx:
"Sets XA audio filter", 2 params) was confirmed against public sources.
Separately, `0x800A61B0` (Stage C's own "a pointer... not identified
yet") is now confirmed to be a real BIOS event descriptor
(`OpenEvent`/`EnableEvent`/`DisableEvent`, matching the public
`F1000000h`+ descriptor range exactly); its third dispatch branch
(`0x80077d78`) was fully decoded and found to be PS1 Root Counter
(Timer) setup, not CD/XA -- ruled out honestly, not left ambiguous.
**Three separate live attempts to catch the command routine actually
firing with `0x0D` found zero hits** -- a real, reported blocker,
narrower in kind than before (the mechanism and protocol are now known;
only the one live observation is still missing). `xa_channel` remains
`POSITIONAL_UNCONFIRMED`. Test count: **497 passed** (492 + 5 in
`test_cdrom_driver_map.py`).

**Seventh follow-up milestone (Capture the Real CD-XA Setfilter Command,
`XA_STREAM_RESOLUTION.md`'s own follow-up section, `gcrts.cdrom_setfilter`)**:
closed the final gap -- a real, live Setfilter call with actual
file/channel values. The previous milestone's zero-hit result turned
out to hide a real bug: the breakpointed address read the command byte
from the wrong stack offset (`sp+0x11` instead of the real `sp+0x12`),
silently returning a plausible-but-wrong `0x00` (Sync) across three
full live sessions, including two real voiced segments playing. A
static scan for every genuine command-register write site (not a
repeat of the same live-capture technique) found the real call sites
and proved the command byte sits in `$v0` directly, no stack-offset
guessing needed. Breakpointing those found real Setfilter traffic
within seconds: **file=2, channel=1**, reproduced byte-identical on a
second independent capture, with `file=2` cross-validated against the
real disc catalog (`XAPACK02.BIN`, a real file). Honestly scoped: no
simultaneous LBA cross-check was taken at the exact capture instant, so
this is live-captured and reproduced, not triple-cross-validated the
way the selector-table chain is. This required an actual live
breakpoint session (not passive polling, unlike every other resolver
in this stack) -- documented as a historical record
(`KNOWN_SETFILTER_OBSERVATIONS`), the same pattern
`KNOWN_CUE_SOURCES` already established. Test count: **506 passed**
(497 + 9 in `test_cdrom_setfilter.py`).

**Eighth follow-up milestone (Audio Event Isolation / Extraction,
`AUDIO_EVENT_EXTRACTION.md`, `gcrts.audio_event_extraction`)**: built
and tested a read-only extraction backend (sector selection filtered by
real CD-XA subheader file/channel/Audio-flag, honest
`ExtractionConfidence` states, never guesses an end boundary from
timing). While verifying whether the Setfilter capture applied to one
specific target event (as the milestone itself required before using
it), a live re-check with a simultaneous position/state read found the
Setfilter is most likely a fixed default/reset value, not proven tied
to any specific event -- a real, honest correction to the previous
milestone's interpretation, recorded permanently
(`gcrts.cdrom_setfilter.is_proven_event_specific()` -> `False`, with
evidence attached), not walked back quietly. The extraction backend
therefore never defaults file/channel from that historical observation.
`event_end_lba` remains unresolved; no `PLAYING -> STOPPED` transition
was observed live this pass either. Test count: **528 passed**
(506 + 22: 14 in `test_audio_event_extraction.py`, 2 in
`test_runtime_snapshot.py`, 6 in `test_cdrom_setfilter.py`
[correction + regression coverage]).

**Ninth follow-up milestone (Per-Event XA Channel Capture,
`CDROM_SETFILTER_CAPTURE.md`)**: armed lifecycle + command monitoring
on the CURRENT live game state (not a reload) for ~460 real seconds
while the user played through and confirmed real, audible playback.
Result: the audio state byte never once transitioned to PLAYING despite
that confirmed playback (a new, honest caveat added to this module's
own lifecycle model, above), and all 8 Setfilter hits observed carried
identical `params=(2, 1)` even as the position counter visited 5
different disc-seek targets. Per the milestone's own explicit failure
handling: this is not a failed search, it's evidence the "one cue, one
Setfilter" model is wrong -- `gcrts.cdrom_setfilter.filter_appears_persistent()`
now records the better-supported alternative: one filter setting
persists across many cycles. Test count: **530 passed** (528 + 2 in
`test_cdrom_setfilter.py`, extending the context-check evidence and
covering the new persistence finding).

**Tenth follow-up milestone (Real Audio Playback Truth,
`AUDIO_PLAYBACK_TRUTH.md`, `gcrts.audio_playback_truth`)**: decoded the
real, previously-captured Setmode value (`0x01`) against public PS1
documentation and found XA-ADPCM and XA-Filter both OFF -- decisive
proof the entire traced `Setloc/Setmode/ReadN/Setfilter` cycle was
never the audio path at all (a plain data-read loop). The documented
XA-audio command, `ReadS` (`0x1B`), has never appeared in any capture
this project has taken. A widened static scan (60 vs. the original 12
instructions) for other command-issuing sites found only false
positives and already-known writes -- no new site. `0x800A6107` is now
formally reclassified in `AudioLifecycleState`'s own docstrings: real
correlation with *some* past session, not confirmed general. No working
replacement "audible playback" signal was found this pass -- reported
honestly as an open question, not forced. Test count: **536 passed**
(530 + 6 in `test_audio_playback_truth.py`).

**Eleventh follow-up milestone (Locate the Real XA-ADPCM Playback Path,
`XA_PLAYBACK_PATH.md`, `gcrts.xa_playback_path`)**: a second live
session (~230+ real seconds, save slot 9 reloaded while armed, user
confirmed the trigger) again produced zero `ReadS` (`0x1B`) hits.
Checked the milestone's own required fallback hypothesis list directly
against the real disc's `.cue` file and found decisive evidence: the
disc has exactly ONE track (`MODE2/2352`, standard PS1 data format) --
genuine CD-DA playback is structurally impossible for this game, ruling
that hypothesis out completely (not just downgrading it). The other
open hypotheses (a different command/path, an incomplete observation
point, a BIOS-side path) remain genuinely open, each with real evidence
attached in `gcrts.xa_playback_path.PLAYBACK_PATH_HYPOTHESES`. The old
traced `ReadN`/Setmode cycle is now permanently classified
`RULED_OUT_AS_XA_AUDIO_PATH`. Test count: **543 passed** (536 + 7 in
`test_xa_playback_path.py`).

**Twelfth follow-up milestone (Secondary CD-ROM Driver Discovery,
`CDROM_DRIVER_DISCOVERY.md`, `gcrts.cdrom_driver_discovery`)**: switched
search technique -- scanned the entire 2MB live RAM image for the raw
CD-ROM register address values directly, instead of scanning code for
the known address-construction pattern. Found 7 additional complete
4-register pointer sets beyond the already-known one. Traced the 3 in
the same page as the known set and found they belong to a broader,
generic interrupt/DMA dispatch table (also holding DMA channel 1/2/3/5
address pairs and `I_STAT`/`I_MASK`) -- real, verified data, but not a
second CD-ROM command-issuing driver. One direct, traced link to the
known audio system was found (a debug-log call referencing the known
command-staging address), not a new functional path. Classified
honestly as `HW_DISPATCH_TABLE_NOT_A_COMMAND_DRIVER`, a category
outside the milestone's own original taxonomy, rather than forced into
an inaccurate existing bucket. Test count: **551 passed** (543 + 8 in
`test_cdrom_driver_discovery.py`).

**Thirteenth follow-up milestone (SPU-Side XA Playback Discovery,
`SPU_AUDIO_PATH_DISCOVERY.md`, `gcrts.spu_audio_path`)**: pivoted from
the exhausted CD-ROM command-side search to the SPU side. A full-RAM
value scan for the SPU base address (`0x1F801C00`) found 7
pointer-holder addresses; tracing from the one adjacent to the known
CD-ROM register block led to a real, live-firing, debug-string-named
function (`"CD_init:addr=%08x\n"`, `0x80081B04`) that sets SPUCNT to
`0xC001` -- psx-spx documents bit 0 as "CD Audio Enable," gating both
CD-DA and XA-ADPCM streaming into the SPU. Confirmed live across two
sessions (6 total firings from 9 known call sites), the strongest
concrete anchor found across all thirteen audio milestones so far.
Two real complications keep this from being a confirmed answer: the
write never once persisted on a later read (reads back `0x0000` every
time), and a combined 300-second live watch (armed alongside the two
real SPU Key ON/OFF writer sites found the same pass) caught `CD_init`
not firing at all in that window while Key ON fired constantly but
almost always with an empty (no-op) voice bitmask. Honest result:
`gcrts.spu_audio_path.classify_playback_backend()` returns `UNKNOWN`,
not a guessed `XA_ADPCM_CONFIRMED` -- no single capture window yet
combined an armed breakpoint with a genuinely confirmed audible
trigger. Test count: **566 passed** (551 + 15 in
`test_spu_audio_path.py`).

**Fourteenth follow-up milestone (Live Audible Trigger Correlation,
`SPU_AUDIO_PATH_DISCOVERY.md`'s own follow-up section,
`gcrts.spu_audio_path`)**: closed the gap the thirteenth milestone left
open. Using the project's own established automated-input technique
(`Keyboard_PadCircle`/'D', `0x44`) to trigger dialogue from save-slot 9
with `CD_init`'s SPUCNT write and all 5 known Key ON/OFF sites armed
beforehand, a live run produced a genuine, decisive result: the user
explicitly confirmed hearing a real voice line during the exact
captured window (script context verifiably changed, proving the
trigger reached the game), while **zero of the 6 armed sites fired
meaningfully** — a real, CPU-register-level-confirmed negative,
ruling out `CD_init` and both Key ON/OFF families as the mechanism for
that instance. Separately, while attempting to poll the full SPU
register block during that same window, discovered and diagnostically
confirmed a second, independent finding: **GDB's own memory read/write
path for the SPU hardware I/O range (`0x1F801xxx`) does not round-trip
even a debug-issued write, while genuinely, verifiably running** (a
direct write-then-readback test failed both immediately and a full
second later, while plain RAM writes round-tripped correctly in the
same session). This retroactively reclassifies the prior milestone's
"`CD_init`'s write does not persist" finding as an unverifiable
tooling limitation, not a confirmed behavioral fact — CPU-register-based
findings (the actual bug this milestone needed to fix along the way:
an earlier "keep the emulator running" helper never re-sent `c` after
PCSX-Redux's per-interrupt halt, silently freezing execution after the
first interrupt) remain unaffected and reliable. Playback backend
stays `UNKNOWN`, now for a stronger, more precise reason: a real
capture window was achieved and decisively rules out the known sites,
rather than never having been achieved at all. Test count: **574
passed** (566 + 8 in `test_spu_audio_path.py`).

**Fifteenth follow-up milestone (PCSX-Redux SPU Observation Channel,
`SPU_OBSERVATION_CHANNEL.md`, `gcrts.pcsx_spu_observer`)**: tooling-
first pivot after the fourteenth milestone confirmed GDB's own memory
read/write path for the SPU hardware I/O range is unreliable. Found
that PCSX-Redux ships a native, built-in SPU debugger (`Debug > SPU >
Show SPU debug`), validated it as a genuine, safely-automatable window
showing real, live-changing hardware state (proven against an
independently-verified state change over ~3 real seconds). A direct
cross-check at the same live instant found GDB reading SPUCNT as
`0x0000` while the native tool showed `CTRL=0xC081` (CD Audio Enable
bit set) — reversing the fourteenth milestone's "the write does not
persist" finding: `CD_init`'s effect genuinely IS live on real
hardware; only GDB's read of it was wrong. A silent-baseline vs.
user-confirmed-audible comparison found CD Audio Enable identically
set in both captures (a persistent, always-on state, not a per-line
toggle) — but could not isolate one specific SPU voice channel as "the
dialogue channel," since background-music/ambience channels were
already active in the silent baseline too. Along the way, recovered
from a real operational mishap (an accidental `--help` CLI invocation
killed the original running emulator instance via PCSX-Redux's
single-instance behavior; recovered cleanly since save-state files are
plain files on disk, unaffected by the process restart) and caught
and immediately deleted two accidental screenshots of an unrelated,
private window before adding a permanent abort-on-unfocus guard to all
further screenshot automation. Test count: **588 passed** (574 + 14 in
`test_pcsx_spu_observer.py`).

**Sixteenth follow-up milestone (Crash-Loop Fix + Synthetic-Input
Limitation, `SPU_OBSERVATION_CHANNEL.md`'s own follow-up section,
`gcrts.pcsx_spu_observer`)**: attempting to isolate a dialogue-specific
SPU channel (the fifteenth milestone's own suggested next step)
surfaced two genuine findings instead. First, a reproducible crash
loop (MIPS cause register decoding to exception code 10 / Reserved
Instruction, PC stuck at `0xA0010000` on every subsequent stop) that
survived both a save-state reload and an in-emulator Hard Reset --
resolved only by fully closing and relaunching the PCSX-Redux process;
the save file itself was verified byte-identical (MD5) to this
project's initial git commit, ruling out a corrupted save.
`crash_loop_requires_full_process_restart()` -> `True`. Second, and
more consequential for future automation: a direct A/B test confirmed
**synthetic keyboard input does not reach the emulated game's
controller** -- real physical key presses advanced dialogue
immediately, while every synthetic-input variant tried did not, even
though the same mechanisms reliably drive PCSX-Redux's own ImGui
menus. `synthetic_input_reaches_game_controller()` -> `False`. This
explains why the fourteenth milestone's automated triggers worked in
that session but could not be reproduced here -- a real environmental
constraint on unattended live-capture automation, not a code
regression. Test count: **592 passed** (588 + 4 in
`test_pcsx_spu_observer.py`).

**Seventeenth follow-up milestone (Manual All-Voices-Muted Experiment
-- Playback Backend Resolved, `SPU_AUDIO_PATH_DISCOVERY.md`'s own
follow-up section, `gcrts.spu_audio_path`)**: attempted first to solve
reliable automated triggering via a virtual XInput gamepad
(`vgamepad`/ViGEmBus, already installed on this machine). Confirmed
Level 1 (device creation) and Level 2 (Windows' own `XInputGetState`
correctly reports real button-state changes, even with the pad created
before PCSX-Redux's own startup) -- but Level 3 (the actual game
responding) never succeeded across every configuration tried. Per this
milestone's own explicit time-boxing instruction, switched to the
manual fallback rather than continuing to debug generic Windows input.
Using PCSX-Redux's native SPU Debug window's per-channel Mute controls
(`Debug > SPU > Show SPU debug`), the user manually muted every SPU
voice channel showing activity during a real, self-triggered dialogue
line -- **the voice line kept playing, completely unaffected**,
reproduced independently in a second, structurally different scene
(one initially suspected to be a pre-rendered movie/FMV segment).
`gcrts.spu_audio_path.all_spu_voices_muted_dialogue_still_audible()`
-> `True`. This is the decisive result the whole sixteen-milestone
audio chain had been building toward: dialogue audio does not go
through the SPU's normal 24-voice mixing engine at all, pointing
directly to the CD input path (the mechanism gated by SPUCNT's CD
Audio Enable bit, already confirmed genuinely and persistently set via
the native SPU debugger). `classify_playback_backend()` now returns
`CD_INPUT_UNKNOWN_FORMAT` -- not `XA_ADPCM_CONFIRMED`, since CD-DA
being structurally ruled out on this disc makes XA-ADPCM the only
realistic remaining candidate by elimination, not something
independently re-verified this pass. Test count: **598 passed** (592 +
6 in `test_spu_audio_path.py`).

**Eighteenth follow-up milestone (Chasing the Exact CD Input Stream
Format, `SPU_AUDIO_PATH_DISCOVERY.md`'s own follow-up section,
`gcrts.spu_audio_path`)**: with the CD input routing confirmed, tried
to independently verify the stream format is genuinely XA-ADPCM.
Static analysis of `CD_init`'s 9 call sites found real structure: 2 of
them (`CD_INIT_GATEKEEPER_SITES`) are gated by a genuine CD-position
change-detection check (`0x800A2E18` cached vs. `0x800A3120` live
target), unlike the other 7's generic retry-after-error pattern.
Live-armed across a real, user-confirmed voice line (two separate
trigger attempts): neither fired --
`cd_init_gatekeeper_sites_fired_during_confirmed_trigger()` -> `False`,
reinforcing from a second angle that `CD_init` is not the per-line
trigger. Separately, re-armed the original 3 known CD-ROM
command-write sites and logged every `Setmode` value (not just the
first sample, as in the original `AUDIO_PLAYBACK_TRUTH.md` finding)
across ~150 real seconds spanning a confirmed voice line: 46 captures,
100% showing `mode_byte=0x01` -- XA-ADPCM and XA-Filter both off,
every single time. A methodological note from the same capture: the
second breakpoint site showed `$v0` sweeping through every value
`0x00`-`0x80` in sequence during one interval -- a loop counter
incidentally reusing that register, not real command traffic;
recorded so a future pass doesn't mistake register noise for commands
again. Playback backend classification is unaffected
(`CD_INPUT_UNKNOWN_FORMAT` stands, the routing finding remains the
strongest evidence), but the specific software Setmode toggle this
project has instrumented is now decisively shown not to be how (or not
the only way) XA-ADPCM decode gets enabled, if it is toggled
explicitly at all. Test count: **602 passed** (598 + 4 in
`test_spu_audio_path.py`).

**Nineteenth follow-up milestone (CD Input Data-Path Identification,
`AUDIO_TRANSPORT_PATH.md`, `gcrts.spu_audio_path`)**: per an explicit
instruction to stop chasing "prove XA-ADPCM" through Setmode/`ReadS`
(both exhausted) and instead ask what actually feeds CD Input during a
confirmed audible line, inventoried PCSX-Redux's Debug menu rather
than assuming raw GDB MMIO was the only option, and found `Debug >
Misc hardware > Show HW Registers` -- a reliable, non-GDB window
exposing all 7 system DMA channels' `MADR`/`BCR`/`CHCR` plus the 3
hardware timers. With a save state positioned right at a confirmed
voice-line moment and the emulator verified genuinely, continuously
running (Timer 1's own counter changed on every one of 25 captured
frames), **DMA channel 3 (CD-ROM) and DMA channel 4 (SPU) showed zero
change whatsoever across the entire window**, while DMA channel 2
(GPU) showed a real, distinct transfer-completion pattern in the same
captures -- ruling out "the emulator was frozen" as an explanation and
making the CD-ROM/SPU silence a genuine negative.
`dma_cdrom_or_spu_channel_active_during_confirmed_voice_line()` ->
`False`. Combined with the earlier finding that no regular SPU voice
carries the dialogue either, this points to CD-ROM audio output
reaching the SPU's CD Input via a direct hardware bus, separate from
the general-purpose DMA controller entirely -- a real PS1 architectural
pattern (DMA channel 3 moves sector data for asset loading, a
different signal path from the CD-ROM's own decoded audio output).
Per the milestone's own explicit instruction, `TransportPath` and
`StreamFormat` are now modeled as separate enums rather than folded
into one classification: `classify_transport_path()` ->
`DIRECT_HARDWARE_AUDIO_BUS`, `classify_stream_format()` -> `UNKNOWN`
(unchanged -- the format question remains genuinely open). The legacy
`classify_playback_backend()` stays `CD_INPUT_UNKNOWN_FORMAT`,
unaffected and consistent with the new separated model. Test count:
**612 passed** (602 + 10 in `test_spu_audio_path.py`).

**Twentieth follow-up milestone (SPU-Internal RAM Inspection Attempt +
XA Panel Correlation, `AUDIO_TRANSPORT_PATH.md`'s "SPU RAM behavior"
section, `gcrts.spu_audio_path`)**: per the prior milestone's own
"next task," tried to find a way to inspect the SPU's internal 512KB
sound RAM directly. Four avenues were checked and closed: PCSX-Redux's
GUI Memory Editor windows (no memory-space selector -- confirmed live
via screenshot, the "Options" menu is display formatting only), the
native SPU Debug window itself (exactly 3 sections -- SPU/XA/Channels
-- no raw memory view), PCSX-Redux's own documented Lua scripting API
(fetched and checked directly: `getMemPtr`/`getParPtr`/`getRomPtr`/
`getScratchPtr`/`getRegisters`/`getReadLUT` cover main RAM, parallel
port, BIOS, scratchpad, and CPU registers/LUT but not SPU RAM; the
only SPU-adjacent Lua function is an offline ADPCM encoder utility,
unrelated to reading live emulator state), and GDB's own SPU MMIO
read/write path (already confirmed stuck-zero on both the KUSEG and
KSEG1 addresses, closing the fallback of manually driving the
real-hardware Sound RAM Transfer Address/FIFO protocol, since that
protocol itself needs a working SPU register write path).
`spu_internal_ram_directly_inspectable()` -> `False` -- a genuine,
well-supported tooling limitation, not a temporary gap.

As a substitute, the SPU Debug window's own live `XA` panel
(Frequency/Stereo/Samples/Volume L/R -- a real, non-zero,
standard-XA-ADPCM-rate `Frequency: 37800` had been spotted in a
screenshot) was tested directly: two independent 60-frame live
captures (~1fps, self-resuming GDB continue loop keeping the emulator
genuinely running, verified via per-channel Position/Current values
actively changing across frames), the second with a user-confirmed
trigger at a precise 9-10s mark. In both captures, every sampled frame
-- spanning well before, at, and long after the trigger -- showed
byte-identical `XA` panel values. One `MEM` field transition was
observed in the second capture, but ~30s after the trigger (too late
to be its effect, and matching the static value the first capture sat
at regardless of any trigger) --
`spu_debug_xa_panel_changed_during_confirmed_voice_line()` -> `False`.
Consistent with, not contradicting, the standing finding that dialogue
bypasses the instrumented parts of the SPU pipeline entirely. Test
count: **619 passed** (612 + 7 in `test_spu_audio_path.py`).

## Starting point

Stage C (`BACKLOG_INVESTIGATION_RESULTS.md`) had already live-traced one
complete chain, every link captured, none inferred:

```
script sound_or_voice_cue (0x0800, param=127)
  -> 0x800760b4 (writes raw params to 0x800a6114-17)
  -> 0x80077808 (dispatches on category==2)
  -> 0x80080d54 (BCD MSF-to-LBA: MSF 28:14:21 -> LBA 126921)
  -> DAT/XA1/XAPACK08.BIN, channel 7, mono 4-bit XA-ADPCM
```

What that trace never established: *when* playback actually starts,
whether it's *currently* playing, *where* it is within the stream, and
*when* it stops. That's this milestone's scope.

## What is CONFIRMED (live-verified this session)

**A real three-state lifecycle**, keyed off `0x800A6107` -- the *second*
byte of the "state pair" Stage C had already found being written but
never correlated with playback activity over time:

| Raw byte | Lifecycle state | Live evidence |
|---|---|---|
| `0x00` | STARTING | Observed only transiently, at the instant a save state carrying a fresh dispatch loads, and again for ~14s immediately after a fresh cue's `last_req_params` was written but before the position counter started moving. |
| `0x01` | PLAYING | Sustained for 37+ real seconds in one poll, 47+ in a live end-to-end run using the actual module -- always co-occurring with the position counter (below) advancing, and with `0x800A6114`'s raw params holding a real, nonzero cue value. |
| `0x02` | STOPPED | Sustained for **57+ consecutive real seconds** with zero movement in one dedicated poll, and independently reconfirmed in the end-to-end run -- always co-occurring with `0x800A6114` cleared to `0x00000000` and the position counter completely frozen. |

Two independent signals agreeing (`0x800A6107`'s value AND
`0x800A6114`'s clear-to-zero) is what makes STOPPED detection solid, not
a single byte's say-so -- `capture_audio_event` explicitly downgrades a
`0x02`+nonzero-params combination to `UNKNOWN` rather than trusting a
never-observed-live combination (see `tests/test_runtime_audio.py::
test_capture_reports_unknown_when_stopped_state_disagrees_with_params`).

**A real, live-verified positive-path proof**, captured by pausing on a
reload of save-state slot 3 and immediately snapshotting:

```
event: script_parameter=127, state=STARTING, confidence=STATIC_LOOKUP
       source_file=DAT/XA1/XAPACK08.BIN, xa_channel=7, start_lba=126921
       position_counter=128044
snapshot.active_audio == [that event, as a dict]
```

**A real, live-verified negative-path proof**, minutes later once the
scene had genuinely finished: `capture_audio_event` returns
`state=STOPPED`, and `capture_runtime_snapshot` correctly reports
`active_audio == []` -- stale finished audio is never reported as
currently active.

**Position genuinely tracks progress**, not just a fixed clock:
`0x800A61AC` (already known from Stage C as the address `0x80080d54`'s
MSF-to-LBA result is stored into) was polled every ~0.6-0.8s across two
independent sessions. While state was PLAYING it increased on almost
every poll, including real multi-second plateaus (consistent with
natural speech pauses -- a fixed-rate timer would never plateau); while
state was STOPPED it was completely static for 57+ seconds straight.

**Multi-cue scenes are handled correctly, confirmed live, not just in
theory**: during the Phase 7 end-to-end run, the dispatched cue actually
changed mid-scene (`script_parameter` 127 -> 126) and the position
counter genuinely reset lower at that exact moment. `capture_audio_event`
already had a rule for this (`position_counter_start` only carries
forward across polls when `script_parameter` is unchanged) written
*before* this specific transition was observed, and the live trace
confirmed it fires correctly, not just in the unit tests that inspired
it.

## What is PARTIAL / not confirmed -- do not overclaim these

- **`0x800A61AC`'s exact real-time unit.** ITS MECHANISM is now
  explained (see `AUDIO_CUE_RESOLUTION.md`, Observation 1): it advances
  because the confirmed dispatch site calls `0x80080d54` repeatedly
  (~6x/second) while a cue is active, each call computing a slightly
  larger LBA than the last and overwriting this address with the fresh
  result -- not a separately-incrementing counter. What is still NOT
  confirmed is why the climb rate (~100-300/sec across sessions) doesn't
  cleanly match a simple real-time-to-sectors conversion; treat
  `position_counter` as a real, live, generally-non-decreasing progress
  signal useful for source resolution (see below) and for detecting
  "is this actively changing right now," not as a calibrated
  millisecond value.
- **`playback_offset_ms`.** Deliberately NOT derived from
  `position_counter`'s own scale. `compute_playback_offset_ms` instead
  sums real wall-clock time across consecutive polls where state stayed
  PLAYING for the same `script_parameter` -- accurate to normal polling
  latency, but only as fine-grained as the caller's own poll cadence,
  and reset to `None`-contributing whenever a gap includes a
  non-PLAYING sample. This remains the right choice, not a stopgap --
  see `AUDIO_CUE_RESOLUTION.md` for why calibrating the counter itself
  turned out to be the wrong direction entirely.
- **Segment/cue-reset semantics.** `AUDIO_CUE_RESOLUTION.md`
  (Observation 2) found something more surprising than a simple reset
  rule: the SAME raw `script_parameter` (127) resolved to two
  *different physical files* across independent real-time captures of
  the identical save state. The determining factor tracks real elapsed
  time since the state loaded, not script position. This means
  `position_counter`'s resets are not simply "one reset per new cue" --
  do not assume that.
- **`source_file`/`xa_channel` resolution.** Superseded design, see
  `AUDIO_CUE_RESOLUTION.md` -- `capture_audio_event` now resolves
  `source_file` LIVE from the observed LBA against the disc's real,
  exact file table (general, not a per-cue guess), falling back to the
  historical `KNOWN_CUE_SOURCES` table only when that fails.
  `xa_channel` is still computed but confirmed to be a positional
  artifact of the disc's 8-way interleave, not proven to reflect actual
  SPU channel selection -- reported under
  `AudioConfidence.POSITIONAL_UNCONFIRMED`, not silently upgraded.
- **PAUSED** is a real enum value (kept for future evidence / other
  audio categories -- music/SFX/ambient may behave differently) but was
  never observed live this session. **REQUESTED** likewise has no
  independently-observed raw value distinct from STARTING's transient
  `0x00` -- it's kept as a conceptual pre-dispatch state per the
  original call-chain trace (`0x800760b4` writes params *before*
  `0x80077808` even runs), not because a separate raw byte was caught
  for it specifically.

## What is UNKNOWN

- Why `0x800A6106` (the byte the pre-existing getter `0x80076118` reads)
  never changed from `0x00` across every observation this session, while
  `0x800A6107` -- one byte over -- carries all the real lifecycle
  information. (An early version of this module actually mis-read the
  two bytes as a single little-endian `u16`, which matched neither
  byte's real value and silently produced `UNKNOWN` for every event --
  caught by testing the model against live memory before trusting it,
  not by code review. See the module's own docstring.)
- Whether music/SFX/ambient categories (this game's own
  `0x80077928`-dispatch categories other than `2`) share this exact
  state machine at all, or have their own.
- Whether a general, static `cue -> descriptor` lookup table/function
  exists anywhere in RAM or in an executable at all. Given the same raw
  parameter value was found meaning different things at different real
  times (`AUDIO_CUE_RESOLUTION.md`, Observation 2), the more likely
  explanation is that `script_parameter` is a small, reused/recycled
  index whose real meaning depends on script execution position -- a
  question outside this RAM-polling tracker's reach without a parallel
  live script-buffer correlation, not attempted this pass.

## How to reproduce

Load save-state slot 3 (the same dialogue scene Stage C's original trace
used) via the PCSX-Redux Web API (`/api/v1/state/load?slot=3`), then:

```python
from gcrts.live_extract import GdbClient
from gcrts.runtime_audio import capture_audio_event

c = GdbClient(port=3334, timeout=10)
event = capture_audio_event(c.read_memory)
print(event)
c.close()
```

Or through the production path (no manual GDB at all):

```python
from gcrts.runtime_visual_provider import RuntimeVisualProvider
from gcrts.runtime_snapshot import capture_runtime_snapshot

provider = RuntimeVisualProvider(projects=[])
frame, objects = provider.scan()
snapshot = capture_runtime_snapshot(provider, frame, objects)
print(snapshot.active_audio)  # [] once the cue has stopped
```

## Definition of Done -- honest accounting

| Question | Status |
|---|---|
| What audio is playing? | PARTIAL -- `script_parameter` is captured live and reliably, but is NOT a stable source identifier by itself (see `AUDIO_CUE_RESOLUTION.md`) |
| Where did it come from? | CONFIRMED, generally -- resolved live from the observed LBA against the disc's own exact file table (`gcrts.xa_disc_index.resolve_lba_to_file`), for any position actually seen, not just cue 127 |
| Which XA channel is active? | PARTIAL -- a real value is computed, confirmed to be a positional artifact of the disc's interleaving, not proven to reflect true SPU channel selection |
| When did it start? | CONFIRMED (raw state transition to `0x00`/STARTING, live-observed) |
| How far into it are we? | PARTIAL -- a real, live, actively-changing signal exists (`position_counter`, now explained as repeated MSF-to-LBA recomputation, `AUDIO_CUE_RESOLUTION.md`); its exact real-time unit/scale is not confirmed |
| Is it still playing? | CONFIRMED (`state == PLAYING`, cross-checked against position advancing) |
| When did it stop? | CONFIRMED (raw state transition to `0x02`/STOPPED, cross-checked against params clearing and position freezing, sustained 57+s) |
| Preserved in a paused `RuntimeSnapshot`? | CONFIRMED -- live-verified: an active event is captured and included; a stopped one is correctly excluded |

## Explicitly not built this pass

Per the milestone's own scope: no waveform editor, no audio extraction
UI, no subtitle editor/rendering, no movie runtime tracking, no full
audio-bank (`PROGHEAD.CDB`/`PROGVAB.CDB`) parser, no SDB work, no
Renderer 2 research, no real-hardware disc validation.

## Recommended next milestone

Extend `KNOWN_CUE_SOURCES` by tracing 2-3 more cues the same way Stage C
traced 127 (the 126 caught live this session during Phase 7 is a ready-
made, already-observed candidate) -- this turns the current one-entry
proof of concept into believable general coverage, and would also be the
natural place to finally pin down `0x800A61AC`'s real unit (comparing
several cues' position-counter behavior against their own known
start LBAs and durations is a much stronger basis for that than one
sample). Movie/subtitle work should stay blocked behind Stage B's own
still-open "which overlay is actually resident during movie playback"
question, unchanged by this milestone.
