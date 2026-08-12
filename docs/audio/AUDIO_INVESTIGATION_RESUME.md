# Audio Investigation — Resume Protocol

A single, actionable "pick up here" document for the next session of
the SPU/XA playback investigation. Read this before re-deriving
anything from `RUNTIME_AUDIO_TRACKER.md`'s full 19-milestone history —
it exists specifically so a fresh session doesn't have to.

## Where things stand right now

- **Confirmed, real, reliable**: `CD_init` (`0x80081B04`) sets SPUCNT
  bit 0 (CD Audio Enable) and this is genuinely, persistently true on
  real hardware — proven via PCSX-Redux's own native SPU debugger
  (`gcrts.pcsx_spu_observer`), not GDB (GDB's own SPUCNT reads are
  confirmed wrong, see below).
- **Confirmed, decisive negative**: none of the known SPU writer sites
  (`CD_init`, both Key ON/OFF site families) fire meaningfully during a
  real, user-confirmed audible dialogue line
  (`gcrts.spu_audio_path.LIVE_CORRELATION_RUNS`).
- **Confirmed tooling fact**: GDB's memory read/write path for
  `0x1F801xxx` (SPU hardware I/O) does not round-trip even a
  debug-issued write while genuinely running. Never trust a raw GDB
  peek of that range as ground truth — use the native `"SPU Debug"`
  window instead (`Debug > SPU > Show SPU debug`,
  `docs/audio/SPU_OBSERVATION_CHANNEL.md`).
- **Confirmed environmental constraint**: synthetic input does **not**
  reach the emulated game controller in this environment. This was
  tested twice: `keybd_event`/`SendInput` keyboard input (does not
  work), and a real virtual XInput gamepad via `vgamepad`/ViGEmBus
  (device creation and Windows-level button state both confirmed
  working via `XInputGetState`, but the game itself never responded
  regardless of whether the pad existed before or after PCSX-Redux's
  own startup, or whether the window had focus). Unattended automated
  dialogue-triggering is therefore not currently possible with any
  method tried so far — see
  `docs/tooling/PCSX_REDUX_CAPTURE_PROTOCOL.md` section 8.
- **RESOLVED — playback backend identified**: a manual all-voices-muted
  experiment (using the native SPU Debug window's per-channel Mute
  controls, with the user physically triggering dialogue) found that
  muting every regular SPU voice channel does **not** silence the
  dialogue line — reproduced independently in a second, structurally
  different scene. `gcrts.spu_audio_path.all_spu_voices_muted_dialogue_still_audible()`
  → `True`. Dialogue audio bypasses the SPU's 24-voice mixing engine
  entirely and enters via the **CD input path** — the mechanism
  SPUCNT's CD Audio Enable bit gates.
  `classify_playback_backend()` now returns `CD_INPUT_UNKNOWN_FORMAT`,
  not `UNKNOWN` — the first confirmed classification this whole audio
  investigation has produced.
- **RESOLVED — the CD input stream's exact format**: a byte-level scan
  of every audio sector across all 43 real `XAPACK*.BIN` files
  (`XAPACK_FORMAT.md`, `gcrts.xapack`) found the exact standard Green
  Book CD-XA real-time-audio submode with `coding_info=0x01` (stereo,
  37800 Hz, 4-bit ADPCM) — from the disc's own physical sector headers,
  not the filename or a debugger reading. `classify_stream_format()`
  now returns `XA_ADPCM`. Cross-validated against two real live LBA
  anchors (`KNOWN_CUE_SOURCES[127]`'s channel 7/LBA `126921` lands
  exactly inside channel 7's own physically-bounded stream in
  `XAPACK08.BIN`). The legacy `classify_playback_backend()` still
  returns `CD_INPUT_UNKNOWN_FORMAT` (kept as-is, backward compatible —
  see `gcrts.spu_audio_path`'s own docstring).
- **Two more confirmed negatives on the format side**: `CD_init`'s 2
  position-change-gated call sites (`CD_INIT_GATEKEEPER_SITES`) were
  live-armed across a real, confirmed voice line twice — neither
  fired. 46 live `Setmode` captures across ~150s spanning a confirmed
  voice line all showed the XA-ADPCM bit off, 100% of the time
  (`setmode_xa_adpcm_bit_ever_observed_set()` → `False`).
- **RESOLVED — the transport question**: stopped chasing Setmode
  entirely and instead found, via PCSX-Redux's native `Debug > Misc
  hardware > Show HW Registers` window (all 7 DMA channels'
  MADR/BCR/CHCR, reliably), that **DMA channel 3 (CD-ROM) and channel
  4 (SPU) show zero activity across an entire confirmed voice-line
  window**, while DMA channel 2 (GPU) shows real transfer activity in
  the same captures (ruling out "frozen emulator" as the explanation).
  `dma_cdrom_or_spu_channel_active_during_confirmed_voice_line()` →
  `False`. Points to a direct hardware audio bus from CD-ROM to SPU CD
  Input, bypassing system DMA entirely — see
  `docs/audio/AUDIO_TRANSPORT_PATH.md`. `TransportPath` and
  `StreamFormat` are now separate enums (no longer folded into one
  classification): `classify_transport_path()` →
  `DIRECT_HARDWARE_AUDIO_BUS`, `classify_stream_format()` → `XA_ADPCM`
  (resolved by a later milestone, statically — see below, not through
  the transport finding itself).
- **RESOLVED — SPU-internal RAM inspection is a confirmed tooling
  blocker, not an open question**: four avenues were checked and
  closed — the GUI Memory Editor windows (no memory-space selector,
  confirmed via screenshot), the native SPU Debug window itself
  (exactly 3 sections: SPU/XA/Channels, no raw memory view),
  PCSX-Redux's documented Lua scripting API (`getMemPtr`/`getParPtr`/
  `getRomPtr`/`getScratchPtr`/`getRegisters`/`getReadLUT` — none reach
  SPU RAM; the only SPU-adjacent Lua function is an offline ADPCM
  encoder, unrelated to reading emulator state), and GDB's own SPU
  MMIO path (already confirmed unreliable on both KUSEG and KSEG1,
  closing the real-hardware-transfer-protocol fallback too).
  `spu_internal_ram_directly_inspectable()` → `False`. As a substitute,
  the SPU Debug window's own live `XA` panel (Frequency/Stereo/
  Samples/Volume L/R) was watched across two independent 60-frame live
  captures — one with a user-confirmed trigger at a precise 9-10s mark
  — and every sampled frame showed byte-identical values, no
  correlation with the trigger.
  `spu_debug_xa_panel_changed_during_confirmed_voice_line()` →
  `False`. See `docs/audio/AUDIO_TRANSPORT_PATH.md`'s "SPU RAM
  behavior" section for full detail.
- **RESOLVED — the XAPACK physical format, event segmentation, and an
  extraction pipeline** (`XAPACK_FORMAT.md`, `AUDIO_ASSET_MODEL.md`,
  `gcrts.xapack`, `gcrts.xapack_catalog`, `gcrts.audio_asset_resolver`):
  worked entirely offline this pass (no live capture). Found strict
  8-way channel interleave with a real, physical per-channel EOF marker
  across all 43 packs (41/43 exactly, 2 minor explainable variations),
  giving up to 343 real, independently-extractable audio streams on the
  disc. Built a stable `AudioAsset` identity (`"<pack>:<channel>"`, not
  the selector value), a working raw+decoded-WAV extraction pipeline,
  and a runtime bridge from `ScriptAudioAssociation` to `AudioAsset`.
  Two real bugs were caught and fixed by this milestone's own
  self-testing before being trusted: a sector-alignment drift bug in
  raw extraction, and a channel-identity confusion bug in the LBA
  resolver (interleaved channels' ranges overlap almost entirely --
  range containment alone picks the wrong channel; the real sector's
  own subheader byte must be read directly). The ADPCM decode math
  itself is high-confidence, but its exact nibble-interleave layout is
  NOT perceptually verified (no audio playback in this environment) --
  see "The actual next task" below.

## Environment setup (do this first, every time)

1. **Check for a stray/crashed process before launching anything.**
   `Get-Process | Where-Object { $_.ProcessName -like '*pcsx*' }`. If
   anything is running and behaving oddly (frozen frame, no FPS
   counter changing), don't try to fix it in place — `Stop-Process`
   both `pcsx-redux` and `pcsx-redux.main`, then relaunch clean. See
   `PCSX_REDUX_CAPTURE_PROTOCOL.md` section 9 for the specific
   crash-loop signature (PC stuck at `0xA0010000`, exception code 10)
   and why an in-place Hard Reset does not fix it.

2. **Launch from the project directory** (so it picks up `pcsx.json`):
   ```powershell
   Start-Process -FilePath "C:\PCSXRedux\drop\binaries\vsprojects\x64\ReleaseWithClangCL\pcsx-redux.exe" -WorkingDirectory "c:\Users\טופז\starter-project"
   ```

3. **Load the disc.** No reliable API/automated path was found this
   session (`File > Open Disk Image` opens a native file dialog that
   automated clicking could not reliably drive) — **ask the user to
   load it manually**: `File > Open Disk Image` →
   `קיבצי דמה\Twilight Syndrome - Tansaku Hen (Japan).cue`. This is a
   one-time step per relaunch, not per test.

4. **Verify the API is up and the disc loaded**, then load save slot 9
   (a real, reproducible pre-voiced-dialogue state):
   ```bash
   curl -s "http://127.0.0.1:8080/api/v1/execution-flow"
   curl -s "http://127.0.0.1:8080/api/v1/state/load?slot=9"
   ```
   `"State slot index 9 load successful."` confirms the disc is
   genuinely loaded (a load against no disc fails).

5. **Verify the CPU is genuinely healthy before doing anything else**
   — do not skip this, it is what would have saved an entire session
   of confused troubleshooting:
   ```python
   # read 'g' (registers), decode cause = (regs[36] >> 2) & 0x1F
   # exc_code 0 = healthy interrupt; anything else (esp. 10) = crash loop, see section 9
   ```

6. **Reopen the SPU Debug window** (does not persist across process
   relaunches): `Debug > SPU > Show SPU debug`. See
   `PCSX_REDUX_CAPTURE_PROTOCOL.md` section 10 for exact click
   coordinates and the working `SendInput`-based click helper pattern.

7. **Keep the emulator genuinely running** (not just GDB-attached) via
   a self-resuming continue loop — a bare `Z0`/one-shot `c` is not
   enough; PCSX-Redux halts on every hardware interrupt with a
   debugger attached, so the loop must resend `c` on every `T`-stop
   packet. See any of `gcrts_runtime_probe`-adjacent scratchpad
   scripts from this session, or `PCSX_REDUX_CAPTURE_PROTOCOL.md`
   section 2.

## The actual next task

The stream-format question itself is now resolved
(`classify_stream_format()` → `XA_ADPCM`, see `XAPACK_FORMAT.md`) via
static/offline disc analysis, exactly the direction this doc previously
recommended. What's left is narrower and concrete: **get a real
listening or reference-decoder verification of
`gcrts.xapack.decode_channel_to_pcm`'s output.**

The decode's core sample math (5-filter-pair PSX ADPCM, identical to
SPU voice ADPCM) is high-confidence, and the implementation passed a
strong structural self-test (correct sample count matching the SPU
Debug window's own independently-observed `Samples: 2016` constant, no
clipping/saturation, non-degenerate variance, a speech-plausible
rise/sustain/decay energy envelope ending in near-silence exactly at
the stream's own EOF marker). But the exact sound-group nibble/byte
interleave layout was implemented from the most commonly cited public
CD-XA documentation, not independently verified against a reference
decoder or by ear — no audio playback was possible in this environment.
Concretely: extract and decode a known channel (e.g.
`XAPACK08.BIN` channel 7, the confirmed dialogue cue) to WAV, and either
play it back for a human listener or diff it against an established
open-source XA-ADPCM decoder (e.g. `vgmstream`/`ffmpeg`, if available)
to confirm the interleave choice was correct. Resolving this once
upgrades confidence for every asset at once, rather than needing a
per-asset re-check.

A secondary, smaller follow-up: this pass's Phase 9-11 (static code
search for the game's own XAPACK-consuming functions, to
cross-validate the disc-structural findings against the executable
itself) was explicitly deprioritized -- no standalone extracted main
executable + disassembly toolchain was available in this environment
this pass (only `CAP0.EXE`, a different overlay, was found locally).
Worth revisiting if a full executable dump becomes available.

Automated triggering remains unsolved (see the environmental
constraint above) — assume any further live-correlation work needs a
human physically present to trigger dialogue and confirm what's heard.

## Don't repeat these dead ends

- Don't try to fix a frozen/unresponsive emulator by reloading the
  save state or Hard Reset alone if the PC-stuck-at-`0xA0010000`
  signature is present — go straight to a full process restart.
- Don't trust any raw GDB read of `0x1F801xxx` (SPU registers) as
  ground truth for anything — always cross-check against the native
  SPU Debug window if the finding matters.
- Don't spend time debugging why `keybd_event`/`SendInput` isn't
  advancing dialogue — it's a confirmed structural limitation, not a
  script bug (section 8 above).
- Don't spend time on a virtual XInput gamepad either without a new
  idea first — `vgamepad`/ViGEmBus was tried, confirmed working at the
  Windows/XInput level, and still didn't get a response from the game;
  repeating the same approach isn't likely to change that.
- Don't re-investigate whether any single SPU voice channel carries
  dialogue — this is now closed: none of them do, confirmed twice.
- Don't screenshot without the abort-on-unfocus guard — see
  `PCSX_REDUX_CAPTURE_PROTOCOL.md` section 11.
- Solo/Mute settings in the SPU Debug window do **not** persist across
  a save-state reload — always re-apply them after each load.
- Don't re-arm `CD_init`'s position-change-gated call sites
  (`CD_INIT_GATEKEEPER_SITES`) hoping for a different result — tried
  twice with a real confirmed trigger, zero hits both times.
- Don't re-capture `Setmode` values at the 3 known command-write sites
  hoping to eventually catch the XA-ADPCM bit set — 46 real captures
  spanning a confirmed voice line never showed it set once; that
  specific software toggle is not the answer.
- When reading a shared breakpoint site's `$v0` as "the command byte,"
  verify the calling convention actually puts a command there first —
  one site was seen sweeping `$v0` through every value `0x00`-`0x80` in
  sequence, which was a loop counter, not 129 real CD-ROM commands.
- Don't re-capture DMA channel 3/4 state hoping for a different
  result — a real, verified-running 25-frame capture spanning a
  confirmed voice line found zero activity on both; that question is
  closed.
- Before trusting *any* "nothing changed" capture as a real negative,
  verify genuine execution happened during it — check a hardware
  timer's own counter changed across frames, or (as this milestone
  did) confirm an unrelated channel/register shows real activity in
  the same captures. An early attempt this pass captured 25 frames of
  a completely frozen emulator and nearly reported it as a negative
  result.
- Don't re-check the GUI Memory Editor windows, the SPU Debug window's
  layout, or PCSX-Redux's documented Lua API for an SPU-RAM view —
  all three were checked and closed (see "RESOLVED — SPU-internal RAM
  inspection" above). SPU RAM is not inspectable through this
  project's current tooling; that's a settled fact, not a gap to keep
  probing.
- Don't re-watch the SPU Debug window's `XA` panel
  (Frequency/Stereo/Samples/Volume L/R) hoping a longer or
  better-timed capture will show a change — two independent 60-frame
  captures, one with a trigger pinned to a precise 9-10s mark, both
  showed zero correlation. That specific live signal is closed too.
