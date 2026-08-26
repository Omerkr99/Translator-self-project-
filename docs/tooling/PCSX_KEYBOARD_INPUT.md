# Programmatic Controller Input via Simulated Keyboard

**Superseded for controller input.** The "one dramatic success" this
doc originally reported (a Cross press opening a menu) turned out to
be PCSX-Redux's own ImGui menu reacting to the OS keystroke, not the
emulated PS1 controller — every later attempt on a different (BIOS)
screen failed despite confirmed OS-level focus. That's actually
consistent with, not a contradiction of, this project's own earlier,
more rigorous finding (`docs/tooling/PCSX_REDUX_CAPTURE_PROTOCOL.md`
sections 8, 12): neither synthetic keyboard nor a real virtual XInput
gamepad ever reaches the emulated controller in this build. **For
emulated controller/pad input, use `gcrts.pcsx_pad_bridge` instead**
(PCSX-Redux's own Lua-exposed hardware-level pad override, confirmed
against the real emulator source and live-tested end-to-end). This
module (`gcrts.pcsx_keyboard_input`) is still genuinely useful for its
other real, confirmed use: driving PCSX-Redux's *own* UI (menus, the
Lua Console itself — see `gcrts.pcsx_lua_console`), where OS-level
`SendInput` does reliably land.

---

Resolves a limitation recorded repeatedly throughout this project's
history: no way to send controller input to the game programmatically.
The prior documented attempt (`docs/status/CURRENT_SYSTEM_STATUS.md`'s
audio narrative) used a virtual XInput gamepad (vgamepad/ViGEmBus) --
validated at the Windows/XInput level but "never got the game itself to
respond." That was one specific mechanism failing, not proof no
mechanism could work.

## What actually works

PCSX-Redux's own `pcsx.json` already has real keyboard bindings
configured (`Keyboard_PadCircle`, `Keyboard_PadCross`, `Keyboard_PadUp`,
etc. -- GLFW key codes). Driving those directly via Windows'
`SendInput` API (hardware-level input injection into the OS input
stream) works. `gcrts/pcsx_keyboard_input.py` is the reusable module;
`PadButton`/`press_button()`/`focus_window()`/`find_window_by_process_name()`
are its public surface.

**Two things had to be discovered empirically, both load-bearing:**

1. **`SendKeys` (message-queue-based simulated input) does not reach
   the game at all**, even with genuine OS-level foreground focus,
   confirmed by direct comparison this session. PCSX-Redux's actual
   input handling doesn't process synthesized `WM_KEYDOWN` messages the
   way a plain UI control would. `SendInput` (which injects at the
   hardware level, indistinguishable from a real keystroke) does reach
   it -- this is the actual fix, not merely "try a different API for
   the same thing."
2. **Genuine foreground focus from an unrelated process is blocked by
   Windows by default** (`SetForegroundWindow` alone silently fails).
   The standard, working fix: `AttachThreadInput` to the current
   foreground window's thread immediately before calling
   `SetForegroundWindow`, confirmed live this session after several
   failed naive attempts (including one that sent a keypress to an
   unrelated background window -- a Chrome tab -- without any
   indication of failure, which is why `focus_window()` polls
   `GetForegroundWindow()` afterward rather than trusting the call's
   own return value).

## A real methodological trap, caught by testing against a moving
## target

The very first live validation of this mechanism sent a `RIGHT` arrow
press to a scene with a visible directional cursor and saw no change --
looking like a dead end. The actual cause: focus had silently landed on
an unrelated window (confirmed by checking `GetForegroundWindow()`
against the intended target), not that input wasn't working. Once focus
was independently confirmed correct and the target window was moved to
the primary monitor, a `Cross` press produced an unambiguous, large
visual change (a system/options menu opened) -- proof the mechanism
works, on the *second* real attempt, not the first apparent failure.

## Japanese button convention

Confirmed directly by the user this session: **Circle is confirm/select,
Cross is cancel/back** -- the reverse of the Western convention many
other games use. `gcrts.pcsx_keyboard_input`'s own module docstring
states this explicitly so a future navigation script doesn't
accidentally assume Cross confirms.

## What this unblocks

- The overlay engine's Stage 4 final verification (a genuine cold boot
  reaching a target scene through real menu navigation, to confirm a
  statically-patched disc image's translation appears in play) --
  previously blocked entirely on "needs a human at the controls."
- Any other part of this project's history that hit the same wall,
  including the movie-loader investigation's still-open ambiguous
  groups (`MKUBI.EXE`/`MNINO.EXE`/`MRIKA.EXE`, `MOVER.EXE`) -- reaching
  their trigger scenes no longer strictly requires a human playing live.

## What this does NOT change

- `gcrts.pcsx_keyboard_input` has no automated test coverage for its
  actual `SendInput`/window-focus calls -- those require a live
  Windows desktop session, the same boundary this project already
  draws around every other GUI/live-emulator module (backend logic
  gets tests; live OS/GUI interaction gets manual verification). The
  VK-code mapping and extended-key-flag logic are pure and tested
  (`tests/test_pcsx_keyboard_input.py`).
- This drives *keyboard* bindings, not a real analog controller --
  fine for this game's own digital D-pad/button scheme, but not a
  general analog-input solution.
