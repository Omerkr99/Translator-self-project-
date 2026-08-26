"""Direct, hardware-level PS1 controller input via PCSX-Redux's own
Lua-exposed pad override -- the real fix for the input-automation
problem `gcrts.pcsx_keyboard_input` (OS-level `SendInput`) never
reliably solved.

This project's own prior history had already established, twice, that
OS-level input injection does not reliably reach the emulated
controller: synthetic keyboard (`SendKeys`/`SendInput`) and even a real
virtual XInput gamepad (`vgamepad`/ViGEmBus, confirmed working at the
Windows/XInput level) both failed a direct A/B test against real
physical presses (`docs/tooling/PCSX_REDUX_CAPTURE_PROTOCOL.md`
sections 8 and 12). A later session's `gcrts.pcsx_keyboard_input`
module got one dramatic apparent success with `SendInput` (a Cross
press opening a menu) but then failed repeatedly on a different (BIOS)
screen -- almost certainly because that one success was PCSX-Redux's
own ImGui menu reacting to the OS-level keystroke, not the emulated
game controller, which is consistent with the earlier, more rigorous
finding rather than contradicting it.

This module instead drives `PCSX.SIO0.slots[1].pads[1].setOverride()` /
`.clearOverride()`, confirmed directly against PCSX-Redux's real
`src/core/pad.cc` source: `poll()` computes
`buttonStatus = pad.buttonStatus & pad.overrides` and packs that value
straight into the SIO response bytes the BIOS/game read. `overrides`
is a persistent mask completely independent of GLFW/ImGui/keyboard
state or window focus -- so none of the previous failure modes apply.

The Lua Console must already be open (Debug > Show Lua Console) --
`PadBridgeClient` then loads (and, if it ever goes silently dead --
see below -- reloads) `pcsx_lua/pad_input_bridge.lua` itself via
`gcrts.pcsx_lua_console.run_lua`, with no manual step needed.

LIVE-CONFIRMED QUIRK, load-bearing for this module's retry logic:
PCSX-Redux's Lua event dispatcher can silently, permanently stop
invoking a "GPU::Vsync" listener for no logged reason (confirmed this
session -- one instance's ack file stayed empty for 7+ real minutes
with commands queued, while a byte-identical fresh reload started
acking immediately; documented at length in
`pcsx_lua/pad_input_bridge.lua`'s own comments, and consistent with
`pcsx_lua/spu_playback_trace.lua`'s own prior "a fresh listener kept
counting normally" finding). `PadBridgeClient.press_button` treats a
timeout as "the listener probably died," not "the mechanism is
broken": it reloads the bridge script once and retries the exact same
command before giving up.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_COMMAND_PATH = DEFAULT_PROJECT_ROOT / "pad_input_command.jsonl"
DEFAULT_ACK_PATH = DEFAULT_PROJECT_ROOT / "pad_input_ack.jsonl"
BRIDGE_SCRIPT_DOFILE = 'dofile("pcsx_lua/pad_input_bridge.lua")'

_VALID_BUTTONS = frozenset(
    {
        "SELECT", "START", "UP", "RIGHT", "DOWN", "LEFT",
        "L2", "R2", "L1", "R1", "TRIANGLE", "CIRCLE", "CROSS", "SQUARE",
    }
)


class PadBridgeTimeout(RuntimeError):
    """Raised when the Lua-side bridge never acked a command -- most
    likely because pcsx_lua/pad_input_bridge.lua was never loaded this
    launch (see module docstring), not a transient timing issue."""


class PadBridgeUnknownButton(ValueError):
    pass


@dataclass
class PadBridgeClient:
    command_path: Path = DEFAULT_COMMAND_PATH
    ack_path: Path = DEFAULT_ACK_PATH
    run_lua: object = None  # gcrts.pcsx_lua_console.run_lua by default; injectable for tests

    def __post_init__(self) -> None:
        if self.run_lua is None:
            from gcrts.pcsx_lua_console import run_lua as _default_run_lua

            self.run_lua = _default_run_lua

    def _last_ack_id(self) -> int:
        if not self.ack_path.exists():
            return 0
        last_id = 0
        for line in self.ack_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            last_id = max(last_id, int(record.get("id", 0)))
        return last_id

    def _send_command_and_wait(self, button: str, hold_frames: int, timeout_seconds: float) -> bool:
        command_id = int(time.time() * 1000)
        self.command_path.write_text(
            json.dumps({"id": command_id, "button": button, "hold_frames": hold_frames}),
            encoding="utf-8",
        )
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if self._last_ack_id() >= command_id:
                return True
            time.sleep(0.05)
        return False

    def press_button(
        self, button: str, hold_frames: int = 8, timeout_seconds: float = 5.0, allow_reload: bool = True
    ) -> None:
        """Presses and releases `button` via the live Lua bridge,
        blocking until the Lua side confirms the release actually
        happened (not merely that the command file was written).

        If no ack arrives within `timeout_seconds`, this is treated as
        the bridge listener having silently died (a real, confirmed
        PCSX-Redux quirk -- see module docstring), not as proof the
        mechanism is broken: with `allow_reload=True` (the default) it
        reloads pcsx_lua/pad_input_bridge.lua fresh via the Lua Console
        and retries the exact same command once before raising
        `PadBridgeTimeout`."""
        button = button.upper()
        if button not in _VALID_BUTTONS:
            raise PadBridgeUnknownButton(f"unknown button {button!r}, expected one of {sorted(_VALID_BUTTONS)}")

        if self._send_command_and_wait(button, hold_frames, timeout_seconds):
            return

        if allow_reload:
            self.run_lua(BRIDGE_SCRIPT_DOFILE)
            time.sleep(0.5)  # let the fresh listener's top-level setup (io.open, etc.) finish
            if self._send_command_and_wait(button, hold_frames, timeout_seconds):
                return

        raise PadBridgeTimeout(
            f"no ack for button {button} within {timeout_seconds}s"
            + (" (after reloading pcsx_lua/pad_input_bridge.lua once)" if allow_reload else "")
            + " -- is the Lua Console open (Debug > Show Lua Console)?"
        )
