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
