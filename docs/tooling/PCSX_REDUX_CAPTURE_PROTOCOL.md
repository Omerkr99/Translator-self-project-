# PCSX-Redux Live-Capture Protocol

Distilled operating procedure for driving PCSX-Redux's GDB stub to do
safe, validated, live memory inspection/modification of this game,
built from repeated failures across a long investigation. Follow this
for any future live-debugging round against this project.

## 1. Process/window identity

PCSX-Redux ships as a thin launcher process (`pcsx-redux`, near-zero
CPU usage) that spawns the real emulator core (`pcsx-redux.main`,
where the GDB server and the actual game window both live). After any
relaunch:

```powershell
Get-Process | Where-Object { $_.ProcessName -like '*pcsx*' } |
  Select-Object Id, ProcessName, CPU
```

Confirm the window handle belongs to the `.main` process's PID
(`GetWindowThreadProcessId`), not the launcher. Update every script's
`hwnd` constant after a relaunch — it changes every time.

## 2. Resuming from a halt

Three different "not running" states look similar but need different
handling:

- **UI Pause** (`Emulation > Pause`, F6): only `Emulation > Start`
  (F5) or the equivalent UI action fixes this. A GDB `continue` does
  **not** override it — the core is not merely GDB-halted, it is
  UI-paused, and packets queue with no effect.
- **Focus-loss "Idle"** (shown in the title bar): triggered by almost
  any window-focus change, including this project's own focus-steal
  helper and even a plain mouse click inside the game's client area.
  Fixed by sending `c` and waiting a **real** settle interval
  (~1.2-1.5s) — a bare `continue_and_wait_for_stop()` (0.03s internal
  sleep) is not enough.
- **Genuine GDB breakpoint halt**: this is the state a live-capture
  script actually wants. Confirm it by checking PC against the
  expected breakpoint address, never by the mere fact that a stop
  arrived.

Always verify a resume actually took effect: read PC, wait, read PC
again, confirm it moved. Do not assume `continue` succeeded.

## 3. Breakpoint arm/disarm discipline

**Never cycle `Z0`/`z0` rapidly in a per-iteration loop.** This
project's stub reliably desyncs under that pattern, producing
pathological alternating stale-hit sequences that look like real
activity but are not (documented at length in
`BREAKPOINT_GENERATION_LOG.md`). The fix: arm every breakpoint needed
for an experiment **once**, then loop only on `continue_and_wait_for_
stop()`, checking the returned PC against the *set* of currently-armed
addresses. Disarm everything once, at the very end.

Assign a generation ID (a simple incrementing counter) each time a
fresh set of breakpoints is armed, and never act on a stop that
doesn't match the current generation's expected PCs — see
`scratchpad/estate.py`'s `EmulatorController`.

## 4. Screenshot capture

**Use `PrintWindow(hwnd, hdc, PW_RENDERFULLCONTENT)`.** `GetDC` +
`BitBlt` reliably returns stale/cached frames on this GPU-accelerated
window, especially after any window resize — this produced a long run
of apparently "frozen" screenshots this project mistook for a genuine
emulator freeze. `PrintWindow` immediately showed correct, live,
different content in the same situation.

One caveat found this round: if the target is **genuinely CPU-halted**
at the very entry of a frame's `DrawOTag` call (before the GPU has
rasterized anything for that frame), *both* `PrintWindow` and `BitBlt`
return solid black — there is nothing to capture yet. Halting one
`DrawOTag` invocation *later* (i.e. after the frame in question has
had a chance to actually render) fixes this.

## 5. Overlay/layout drift

This game loads different code into the same address ranges depending
on context (menus vs. gameplay vs. different chapters). Re-validate
every landmark byte-for-byte after **any** of: a process relaunch, a
quickload, a chapter/rumor transition, or an extended idle period on a
menu screen. A full wipe to all-zero bytes at previously-valid
addresses means the relevant module simply isn't loaded yet (e.g.
still on a title/menu screen) — wait for actual gameplay, not a code
bug.

## 6. Dialogue-advance input

The in-game key to advance/confirm dialogue is **`D`**, not `X`/Cross
as long assumed. Always confirm the current control mapping with the
person actually holding the controller before assuming a keycode.

## 7. Multiple dialogue renderers

Do not assume one dialogue-rendering code path covers every on-screen
text box. This game has at minimum: plain conversation boxes, a
separate portrait/photo-inset box style, and a full-screen multiple-
choice menu layer — confirmed to use at least two genuinely different
rendering mechanisms. Identify which visual style is on screen (via a
verified screenshot) before trusting a "no hits" result as evidence of
a broken breakpoint rather than a mismatched scene type.

## 8. Synthetic keyboard input does NOT reach the game

Confirmed via a direct A/B test: real physical key presses advance
dialogue immediately; every synthetic-input variant tried
(`keybd_event` with Circle/`D` or Cross/`X`, `SendInput` with a raw
scancode, each preceded by explicit window-focus and click-to-focus
steps) does **not** reach the emulated controller — even though the
exact same mechanisms reliably drive PCSX-Redux's own ImGui menus
(File/Debug menu clicks, Solo/Mute button clicks all work). This is
consistent with the emulator's controller backend reading raw input
state that filters out OS-injected synthetic key events. **Any
unattended live-trigger automation needs either a human physically
present to provide the dialogue-advance input, or a virtual
gamepad/XInput device** — do not spend time debugging synthetic
keyboard input further; it is a structural limitation, not a bug in
this project's scripts.

## 9. A real crash loop, and how to tell it apart from a normal halt

A genuine crash (not one of the three halt states in section 2) looks
like: every subsequent GDB stop reports the exact same PC, with the
`cause` register decoding to exception code 10 (Reserved Instruction)
— e.g. `pc=0xA0010000`, `cause=0x00000028`. Decode the exception code
from register index 36 (`cause`) as `(cause >> 2) & 0x1F`; code `0`
means a normal interrupt (healthy), anything else is a real fault.

**Neither a save-state reload nor an in-emulator Hard Reset
(`Emulation > Hard Reset`, Shift+F8) fixes this** — both leave the
same fault recurring immediately. Before assuming a save file is
corrupted, verify it against git (`git show HEAD:<file> | cmp - <file>`,
or compare MD5 hashes) — a byte-identical match to a previously-good
commit rules out save corruption and points to accumulated internal
state in the *running process itself* (plausibly from many GDB
attach/detach cycles across a long session). **The only fix found:
fully close and relaunch the PCSX-Redux process** (`Stop-Process` on
both `pcsx-redux` and `pcsx-redux.main`, then `Start-Process` again
from the project directory so it picks up `pcsx.json`), reload the
disc image, then reload the save state.

## 10. The native SPU Debug window (non-GDB SPU observation)

GDB's own memory read/write path for the SPU hardware I/O range
(`0x1F801xxx`) is confirmed unreliable — a debug-issued write does not
round-trip even while genuinely running (see
`docs/audio/SPU_AUDIO_PATH_DISCOVERY.md`'s and
`docs/audio/SPU_OBSERVATION_CHANNEL.md`'s follow-up sections for the
full evidence). For true SPU hardware state, use PCSX-Redux's own
built-in debugger instead: **`Debug > SPU > Show SPU debug`** opens a
window titled exactly `"SPU Debug"` (a genuine, separately-titled OS
window, safely automatable via `EnumWindows`/screenshot once opened).
It shows real SPUCNT/SPUSTAT/XA parameters and all 24 voice channels
(On/Off/Mute/Solo, live waveform plot, frequency, position) reading
the emulator's true internal state, bypassing the unreliable GDB path
entirely. Menu click sequence (coordinates relative to the main
`"PCSX-Redux"` window's own rect, confirmed stable across relaunches
at a `1200x955`-ish default window size): `Debug` menu at
`(left+263, top+42)` → hover/click `SPU` row at `(left+260, top+153)`
→ click the `"Show SPU debug"` leaf item at `(left+460, top+153)`.
Use `SendInput`-based mouse clicks, not `mouse_event`/`SetCursorPos`
— the latter was unreliable for opening ImGui menu dropdowns in this
build.

## 11. Screenshot safety: verify focus immediately before AND during capture

A blind screenshot (grab whatever is at a remembered window rect
without re-checking) can capture an unrelated window if it happened to
come to the foreground in the gap between focusing and capturing —
this happened twice in one session (an unrelated private window was
nearly saved both times; both captures were deleted immediately
without being acted on). **Always re-verify `GetForegroundWindow() ==
target_hwnd` immediately before `GetWindowRect`, and again immediately
before `ImageGrab.grab`/`PrintWindow`, aborting without saving if
focus moved at either check.** Never widen a capture region beyond the
target window's own rect "just in case" — that only increases the
chance of picking up an unrelated overlapping window.

## 12. A virtual XInput gamepad was tried and did not solve input either

`pip install vgamepad` (wraps ViGEmBus, which was already installed on
this machine — check via
`Get-PnpDevice | Where-Object { $_.FriendlyName -like '*Vigem*' }`,
look for `"Nefarius Virtual Gamepad Emulation Bus"` with `Status: OK`)
successfully creates a virtual XInput device, and Windows' own
`XInputGetState` correctly reports real button-state changes from it
(confirmed: `wButtons` bit set, `dwPacketNumber` incrementing on each
press). **This still did not get PCSX-Redux's emulated game to
respond** — tried with the pad created after PCSX-Redux's own startup,
before its startup (so it would be enumerated fresh), and with/without
explicit window focus on the main PCSX-Redux window first. Section 8's
conclusion stands regardless of input method: something about this
specific PCSX-Redux build's controller-reading path does not react to
programmatically-driven input, synthetic keyboard or virtual gamepad
alike. Don't re-attempt either approach without a genuinely new idea
(e.g. inspecting PCSX-Redux's own SDL/controller-selection
configuration for an explicit device-binding step neither approach
tried).

## 13. SPU Debug Solo/Mute state does not persist across a save-state reload

Toggling a channel's `Solo`/`Mute` button in the native SPU Debug
window is a debugger-UI setting, not part of the emulated console
state — but it still gets reset to default (nothing soloed/muted) every
time a save state is loaded, even though the window itself stays open.
**Always re-apply Solo/Mute after every `state/load` call**, not just
once per session. Also note: clicking a `Mute` button while a different
channel has `Solo` active appears to clear that channel's Solo state
as a side effect — verify Solo is still engaged (screenshot, check the
button is highlighted) after touching any other channel's controls,
don't assume it survived.

## 14. The native HW Registers window (DMA/timer/interrupt state)

`Debug > Misc hardware > Show HW Registers` opens a window titled
exactly `"HW Registers"` showing `I_STAT`/`I_MASK`, `DPCR`/`DICR`, all
7 DMA channels' `MADR`/`BCR`/`CHCR` (channel 3 = CDROM, channel 4 =
SPU), the 3 hardware timers (`count`/`mode`/`target`), and Memory
Control — reliably, bypassing the same GDB-SPU-MMIO unreliability
documented in section 10. It defaults to a narrow width that truncates
`CHCR` values; resize it wider (`MoveWindow`) before screenshotting.
Menu click sequence from the main window: `Debug` at `(left+263,
top+42)` → `Misc hardware` row at `(left+285, top+194)` → `Show HW
Registers` at `(left+470, top+193)` (the submenu flies out to the
right of the hovered row, not below it).

**Critical: this window shows genuinely frozen values if the emulator
is not actually running** — an early capture this session mistook a
completely paused emulator (no keep-running loop established) for a
real "nothing changed" result. Always verify genuine execution during
any capture using this window, e.g. check a timer's own `count` value
changed between frames, or confirm at least one DMA channel shows real
activity in the same captures (a channel with zero activity is only
meaningful evidence if some other channel in the same window proves
execution was genuinely happening).

## 15. The "SPU Debug" window's full layout, and where SPU-internal RAM is NOT exposed

The full "SPU Debug" window (section 10) is exactly three collapsible
sections, confirmed via a full-window screenshot: `SPU`
(`IRQ`/`CTRL`/`STAT`/`MEM`), `XA` (`Frequency`/`Stereo`/`Samples`/
`Volume L`/`Volume R`), and `Channels` (per-voice On/Off/Mute/Solo/
Noise/FMod/waveform-plot/Frequency/Position). There is no raw
memory/hex byte view anywhere in it — don't go looking for one.

**None of PCSX-Redux's memory-inspection tools reach the SPU's
internal 512KB sound RAM** (distinct from the MMIO control registers
covered above): the GUI Memory Editor windows (`Memory Editor #1`-`#8`
plus the named Parallel Port/Scratch Pad/Hardware Registers/BIOS/VRAM
presets) have no memory-space selector — their `Options` button is
display formatting only (column count, hex casing, ASCII panel,
zero-greying), confirmed live via screenshot. PCSX-Redux's own
documented Lua scripting API
(`pcsx-redux.consoledev.net/Lua/memory-and-registers/`) exposes
`PCSX.getMemPtr()` (main RAM), `getParPtr()` (parallel port),
`getRomPtr()` (BIOS), `getScratchPtr()` (scratchpad),
`getRegisters()`, and `getReadLUT()` — none of which reach SPU RAM;
the only SPU-adjacent Lua function (`Adpcm:processSPUBlock()`/
`:finishSPU()`) is an offline ADPCM *encoder* utility for authoring
sample data, unrelated to reading live emulator state. Combined with
the already-documented GDB SPU-MMIO unreliability (section 10, both
address segments), this is a genuine, thoroughly-checked tooling
blocker — don't re-open this search without a fundamentally new idea
(e.g. a different emulator build, or source-level access to
PCSX-Redux's own C++ core).

The `XA` panel's live values (`Frequency`/`Stereo`/`Samples`/
`Volume L`/`Volume R`) are visible and update, but were tested directly
against a precisely-timed confirmed voice-line trigger (two 60-frame
captures) and showed **zero correlation** — don't treat a static,
non-zero `Frequency` reading (e.g. `37800`, a real XA-ADPCM rate) as
evidence of active playback; it appears to be a resting/default value
that doesn't react to individual dialogue events.
