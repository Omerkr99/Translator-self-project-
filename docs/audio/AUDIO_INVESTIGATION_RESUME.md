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
- **Still open**: the CD input stream's exact format. XA-ADPCM is the
  only realistic candidate by elimination (CD-DA is structurally ruled
  out on this disc, `XA_PLAYBACK_PATH.md`) but was not independently
  re-verified — `CD_INPUT_UNKNOWN_FORMAT`, not `XA_ADPCM_CONFIRMED`.
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
  `DIRECT_HARDWARE_AUDIO_BUS`, `classify_stream_format()` → `UNKNOWN`
  (still open — the format question is unaffected by the transport
  finding).

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

Find a way to inspect the PS1 SPU's **internal 512KB RAM content**
directly (not just its MMIO-mapped control registers) during a
confirmed voice line, to check for a decoded-sample buffer. This is
the one transport-adjacent question the DMA finding couldn't answer:
SPU-internal RAM is not part of the CPU's normal address space and
isn't reachable through either GDB's (already-unreliable) MMIO path or
the `HW Registers` window used for the DMA finding. Check whether
PCSX-Redux's `Debug > SPU` submenu (only `Show SPU debug` was explored
so far) or the SPU Debug window itself exposes any RAM-content view,
before assuming a new tool is needed.

Independently verifying the CD input stream's exact format
(`classify_stream_format()` → `UNKNOWN`) remains the underlying goal,
but every software-side avenue tried so far (`CD_init`'s real
per-event candidates, the known Setmode dispatch site) has come back
negative — this next task is transport-side, not command-side.

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
  closed. Do check SPU-internal RAM instead (see next task).
- Before trusting *any* "nothing changed" capture as a real negative,
  verify genuine execution happened during it — check a hardware
  timer's own counter changed across frames, or (as this milestone
  did) confirm an unrelated channel/register shows real activity in
  the same captures. An early attempt this pass captured 25 frames of
  a completely frozen emulator and nearly reported it as a negative
  result.
