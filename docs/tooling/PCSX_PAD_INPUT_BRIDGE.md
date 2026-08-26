# Direct, Hardware-Level Pad Input via PCSX-Redux's Own Lua API

The real fix for programmatic PS1 controller input, replacing the
OS-level `SendInput` approach in `docs/tooling/PCSX_KEYBOARD_INPUT.md`
(superseded for this specific purpose — see that doc's own note).

## Why OS-level input injection never worked

This project spent a long time on OS-level input automation and found
all of it structurally unreliable against the emulated controller:

- Synthetic keyboard (`SendKeys`, then `SendInput`) and a real virtual
  XInput gamepad (`vgamepad`/ViGEmBus, confirmed working at the
  Windows/XInput level) both failed a direct A/B test against real
  physical presses (`docs/tooling/PCSX_REDUX_CAPTURE_PROTOCOL.md`
  sections 8 and 12).
- A later session's one apparent `SendInput` success (a Cross press
  opening a menu) was PCSX-Redux's own ImGui menu reacting to the OS
  keystroke, not the emulated controller — not a contradiction of the
  earlier finding, just a false positive from testing on a screen
  where the two are easy to confuse.

## The actual mechanism

Fetched directly from PCSX-Redux's real `src/core/pad.cc` source (not
from memory or documentation) this session:

- `Pads::setLua()` registers, per pad slot, `getButton`, `setOverride`,
  `clearOverride`, `setAnalogMode`, `map` under
  `PCSX.SIO0.slots[pad+1].pads[1]`, plus button-index constants under
  `PCSX.CONSTS.PAD.BUTTON.*`.
- `setOverride(button)` clears that bit in a persistent `overrides`
  mask (`pad.cc` line ~1329); `clearOverride(button)` sets it back.
- `Pad::poll()` computes `buttonStatus = pad.buttonStatus & pad.overrides`
  (line ~811) and packs that value straight into the SIO response
  bytes the BIOS/game actually read (lines ~842-871) — `pad.buttonStatus`
  itself gets *overwritten from real keyboard/gamepad input* every
  poll, but `overrides` is untouched by that and persists until
  explicitly cleared.

This means `setOverride(button)` forces that button "pressed" in the
real hardware-facing data, regardless of real keyboard/gamepad state,
completely bypassing GLFW/ImGui/window-focus — none of the previous
failure modes apply. Confirmed live this session via a direct
`pcall`-wrapped console call before building anything around it.

## Architecture

```
gcrts.pcsx_pad_bridge.PadBridgeClient   (Python, your code calls this)
        |  writes pad_input_command.jsonl, polls pad_input_ack.jsonl
        v
pcsx_lua/pad_input_bridge.lua           (runs inside PCSX-Redux)
        |  every ~10Hz (idle) via a GPU::Vsync listener
        v
PCSX.SIO0.slots[1].pads[1].setOverride()/.clearOverride()
```

Both files live in the repo root because that's PCSX-Redux's own
working directory when launched from this project (confirmed via
`psutil.Process(pid).cwd()`, same as `pcsx_lua/dump_ram.lua`'s
pre-existing relative-path convention).

## Setup

1. Debug > Show Lua Console (once — there is no remote Lua-exec HTTP
   endpoint in this build, confirmed in
   `docs/audio/SPU_OBSERVATION_CHANNEL.md`: `/api/v1/lua`, `/lua/exec`,
   `/execute`, `/eval` all 404).
2. From Python: `gcrts.pcsx_pad_bridge.PadBridgeClient().press_button("CIRCLE")`
   — this loads (and, if needed, reloads) the bridge script itself via
   `gcrts.pcsx_lua_console.run_lua`, no manual `dofile` needed.

## Two real, load-bearing quirks found live this session

1. **A `GPU::Vsync` listener can silently, permanently stop firing, for
   no logged reason.** One instance's ack file stayed empty for 7+
   real minutes with commands queued and waiting, while a
   byte-identical fresh reload started acking within milliseconds —
   consistent with `pcsx_lua/spu_playback_trace.lua`'s own prior
   finding ("a fresh listener kept counting normally" while an older
   one died). `PadBridgeClient.press_button` treats a timeout as "the
   listener probably died," not "the mechanism is broken": it reloads
   the bridge script once and retries the exact same command before
   raising. In practice this costs one extra ~2s cycle occasionally;
   most calls that hit a live listener return in well under a second.
2. **`gcrts.pcsx_lua_console`'s click-target offset for the Lua
   Console's input field is not a stable constant.** ImGui's docking
   layout stores panel splits as *fractions* of the available space,
   not fixed pixel sizes — after the main window has been resized to
   any other size at any point in the session, the Lua Console panel
   can come back at a different width/position the next time the
   window returns to the module's standard size, even though nothing
   in the code changed. Caught live: an offset measured right after a
   fresh launch stopped landing after an unrelated 1500x950 resize and
   back. If `run_lua` calls stop echoing into the console (verify with
   a screenshot — the typed text simply won't appear as a new `# ...`
   line), remeasure `INPUT_FIELD_OFFSET_X/Y` from a fresh screenshot
   rather than assuming the mechanism itself broke.

## What this does NOT change

- `gcrts.pcsx_keyboard_input` is still the right tool for driving
  PCSX-Redux's *own* UI (menus, the Lua Console text field itself) —
  OS-level `SendInput` reliably reaches ImGui there. It's simply the
  wrong tool for emulated controller input, which is what this doc's
  mechanism replaces it for.
- No automated test coverage exists (or can meaningfully exist) for
  the actual live Lua/window-automation calls — same convention as
  every other live/GUI module in this project. `tests/test_pcsx_pad_bridge.py`
  covers the pure file-protocol and reload/retry logic with an
  injected fake `run_lua`.
