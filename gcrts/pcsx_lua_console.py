"""Drives PCSX-Redux's own in-app Lua Console via OS-level input
automation -- NOT an attempt to reach the emulated game controller
(that path is confirmed unreliable, see `gcrts.pcsx_pad_bridge`'s
docstring). This module only needs to reach PCSX-Redux's own ImGui
text input, which this project's own live testing confirmed DOES
receive synthetic `SendInput` events reliably (menu clicks were already
known to work; Unicode-mode key injection into an ImGui text field was
newly confirmed live this session) -- consistent with
`docs/tooling/PCSX_REDUX_CAPTURE_PROTOCOL.md` section 8's finding that
OS-level input reaches PCSX-Redux's own UI just fine, only the emulated
controller-reading path ignores it.

WHY THIS EXISTS: there is no remote Lua-exec HTTP endpoint in this
build (confirmed in `docs/audio/SPU_OBSERVATION_CHANNEL.md` --
`/api/v1/lua`, `/lua/exec`, `/execute`, `/eval` all 404). This is the
only way to get a Lua command into a running instance without a human
manually typing it.

LIVE-CONFIRMED QUIRK #1: PCSX-Redux's own docked-panel layout does not
rescale live when the outer window is resized via `SetWindowPos` from
an external process while at an unusual size (only the OS window
chrome grows; the ImGui content stays pinned at its old pixel size
until the app itself processes the resize). `run_lua` always forces
the window back to `STANDARD_WINDOW_*` first so a resize actually
takes effect before locating the input field.

LIVE-CONFIRMED QUIRK #2, more important: `INPUT_FIELD_OFFSET_X/Y` is
NOT a stable constant. ImGui's docking layout stores each panel's
split as a *fraction* of the available space, not a fixed pixel
size -- so after this window has been resized to some other size at
any point in the session (even briefly, even by this same module), the
Lua Console panel can come back at a different width/position the next
time the window returns to `STANDARD_WINDOW_WIDTH`/`_HEIGHT`, even
though the offset constants haven't changed. This was caught live this
session: an offset measured right after a fresh launch (760, 516)
silently stopped landing on the input field after the window had been
resized to 1500x950 and back, because the panel split ratio had
shifted and the real input field had moved to (565, 498). **If
`run_lua` calls stop echoing into the console (check with a screenshot
-- the typed text simply won't appear as a new `# ...` line), remeasure
this offset from a fresh screenshot rather than assuming the mechanism
itself broke.**
"""
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes
from dataclasses import dataclass

from gcrts.pcsx_keyboard_input import FocusResult, find_window_by_process_name, focus_window

user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008
SWP_SHOWWINDOW = 0x0040
VK_RETURN = 0x0D

# Standardized window geometry, and the Lua Console input field's
# offset from the window's top-left corner within it -- both measured
# live this session against a real running instance (see
# docs/tooling/PCSX_LUA_CONSOLE_BRIDGE.md). Assumes the Lua Console
# panel is already docked/open in its default position (Debug > Show
# Lua Console) -- this module does not open it for you.
STANDARD_WINDOW_X = 100
STANDARD_WINDOW_Y = 50
STANDARD_WINDOW_WIDTH = 800
STANDARD_WINDOW_HEIGHT = 600
INPUT_FIELD_OFFSET_X = 565
INPUT_FIELD_OFFSET_Y = 262


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long), ("dy", ctypes.c_long), ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    ]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUT_UNION)]


def _send_input(inp: _INPUT) -> None:
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))


def _click_at(x: int, y: int) -> None:
    user32.SetCursorPos(x, y)
    _send_input(_INPUT(type=INPUT_MOUSE, u=_INPUT_UNION(mi=_MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTDOWN, 0, None))))
    time.sleep(0.05)
    _send_input(_INPUT(type=INPUT_MOUSE, u=_INPUT_UNION(mi=_MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTUP, 0, None))))


def _type_unicode(text: str) -> None:
    for ch in text:
        _send_input(_INPUT(type=INPUT_KEYBOARD, u=_INPUT_UNION(ki=_KEYBDINPUT(0, ord(ch), KEYEVENTF_UNICODE, 0, None))))
        _send_input(_INPUT(type=INPUT_KEYBOARD, u=_INPUT_UNION(ki=_KEYBDINPUT(0, ord(ch), KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, None))))
        time.sleep(0.01)


def _press_enter() -> None:
    scan = user32.MapVirtualKeyW(VK_RETURN, 0)
    _send_input(_INPUT(type=INPUT_KEYBOARD, u=_INPUT_UNION(ki=_KEYBDINPUT(0, scan, KEYEVENTF_SCANCODE, 0, None))))
    time.sleep(0.05)
    _send_input(_INPUT(type=INPUT_KEYBOARD, u=_INPUT_UNION(ki=_KEYBDINPUT(0, scan, KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP, 0, None))))


class LuaConsoleUnavailable(RuntimeError):
    pass


@dataclass
class LuaRunResult:
    hwnd: int
    focus: FocusResult


def run_lua(code: str, process_name: str = "pcsx-redux.main") -> LuaRunResult:
    """Types `code` into the running instance's already-open Lua
    Console and presses Enter. Does not wait for or capture the
    result -- callers needing to know the outcome should have `code`
    write to a file and poll for it (see `gcrts.pcsx_pad_bridge`)."""
    hwnd = find_window_by_process_name(process_name)
    if hwnd is None:
        raise LuaConsoleUnavailable(f"no visible window found for process {process_name!r}")

    user32.SetWindowPos(hwnd, None, STANDARD_WINDOW_X, STANDARD_WINDOW_Y, STANDARD_WINDOW_WIDTH, STANDARD_WINDOW_HEIGHT, SWP_SHOWWINDOW)
    time.sleep(0.2)

    focus = focus_window(hwnd, timeout_seconds=3.0)
    if not focus.success:
        raise LuaConsoleUnavailable(f"could not bring window {hwnd} to the foreground")

    _click_at(STANDARD_WINDOW_X + INPUT_FIELD_OFFSET_X, STANDARD_WINDOW_Y + INPUT_FIELD_OFFSET_Y)
    time.sleep(0.15)
    _type_unicode(code)
    time.sleep(0.1)
    _press_enter()

    return LuaRunResult(hwnd=hwnd, focus=focus)
