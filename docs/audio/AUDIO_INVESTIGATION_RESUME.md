# Audio Investigation — Resume Protocol

A single, actionable "pick up here" document for the next session of
the SPU/XA playback investigation. Read this before re-deriving
anything from `RUNTIME_AUDIO_TRACKER.md`'s full 16-milestone history —
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
- **Confirmed environmental constraint**: synthetic keyboard input
  (`keybd_event`/`SendInput`) does **not** reach the emulated game
  controller in this environment, even though it reliably drives
  PCSX-Redux's own UI. Unattended automated dialogue-triggering is
  therefore not currently possible — see
  `docs/tooling/PCSX_REDUX_CAPTURE_PROTOCOL.md` section 8.
- **Still open**: which single SPU voice channel (if any single one)
  is responsible for dialogue audio specifically, as opposed to
  background music/ambience (which is active in every "silent"
  baseline captured so far).
- Playback backend classification remains honestly `UNKNOWN`
  (`gcrts.spu_audio_path.classify_playback_backend()`).

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

Per `docs/audio/SPU_OBSERVATION_CHANNEL.md`'s own "Next milestone":

> Build or adopt a synthetic-input path the emulator's controller
> backend actually accepts (e.g. a virtual XInput/DirectInput device),
> then find or construct a scene genuinely free of background music
> and repeat the silent-vs-audible SPU Debug comparison to isolate the
> dialogue channel.

Two independent sub-problems, either one alone would be progress:

1. **Input**: a virtual gamepad (e.g. via `vgamepad`/ViGEmBus on
   Windows) that PCSX-Redux's controller backend can see, to restore
   unattended automated triggering. Confirm with the same A/B test
   pattern (real press vs. synthetic press) before trusting it.
2. **Channel isolation**: without solving (1), this requires a human
   physically present to trigger dialogue while SPU Debug is observed
   — either live narration ("I'm pressing now") or the Solo-button
   technique already built and proven functional this session (click
   a channel's `S` button, trigger, ask what's audible) to directly
   identify which channel carries the voice.

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
- Don't screenshot without the abort-on-unfocus guard — see
  `PCSX_REDUX_CAPTURE_PROTOCOL.md` section 11.
