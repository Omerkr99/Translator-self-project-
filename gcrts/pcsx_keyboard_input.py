"""Programmatic PS1 controller input for PCSX-Redux via simulated
keyboard events -- the capability this project's own history had
repeatedly recorded as missing (`docs/status/CURRENT_SYSTEM_STATUS.md`'s
audio narrative: "a virtual XInput gamepad was validated at the
Windows/XInput level but never got the game itself to respond").

That earlier attempt used a virtual XInput gamepad (vgamepad/ViGEmBus)
-- a different mechanism from this one. PCSX-Redux's own configured
input bindings (`pcsx.json`'s `Keyboard_Pad*` fields) are real GLFW key
codes for actual keyboard keys, and this module drives those directly
via Windows' `SendInput` API (hardware-level input injection, distinct
from `SendKeys`/`PostMessage`, which only reach the window message
queue and were found this session to NOT be picked up by PCSX-Redux's
own input handling).

Two real, non-obvious things had to be fixed empirically before this
worked, both preserved here rather than left to be rediscovered:

1. **Genuine OS-level foreground focus is required, and is non-trivial
   to obtain from an unrelated process.** `SetForegroundWindow` alone
   is silently blocked by Windows' anti-focus-stealing heuristic; the
   standard, working fix is `AttachThreadInput` to the current
   foreground window's thread before calling it (`focus_window` below).
2. **Arrow keys (and other "extended" keys) need `KEYEVENTF_EXTENDEDKEY`.**
   Without it, the synthesized scancode can resolve to the numpad
   equivalent instead of the real arrow key, which will not match
   PCSX-Redux's configured binding. Letter-key buttons (Cross/Circle/
   Square/Triangle/the shoulder buttons) don't need this flag.

Button naming follows this game's own convention as confirmed live
this session: it's a Japanese title, so **Circle is confirm/select and
Cross is cancel/back** -- the reverse of the Western convention many
other games use. Don't assume Cross is "confirm" when scripting a
navigation sequence for this game.
"""
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes
from dataclasses import dataclass
from enum import Enum

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
KEYEVENTF_EXTENDEDKEY = 0x0001


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", _KEYBDINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUT_UNION)]


class PadButton(str, Enum):
    CIRCLE = "CIRCLE"
    CROSS = "CROSS"
    SQUARE = "SQUARE"
    TRIANGLE = "TRIANGLE"
    UP = "UP"
    DOWN = "DOWN"
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    START = "START"
    SELECT = "SELECT"
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    R1 = "R1"
    R2 = "R2"
    R3 = "R3"


# Win32 virtual-key codes, one per PadButton, derived from this
# project's own pcsx.json Keyboard_Pad* bindings. For letter-key
# bindings (ASCII A-Z), the GLFW key code in pcsx.json numerically
# equals the VK code, so no translation table was needed for those;
# the special keys (arrows/Enter/Backspace) use GLFW codes with no such
# coincidence, so they're mapped explicitly here instead of assumed.
DEFAULT_VK_MAP: dict[PadButton, int] = {
    PadButton.CIRCLE: 0x44,  # 'D' -- pcsx.json Keyboard_PadCircle=68
    PadButton.CROSS: 0x58,  # 'X' -- Keyboard_PadCross=88
    PadButton.SQUARE: 0x5A,  # 'Z' -- Keyboard_PadSquare=90
    PadButton.TRIANGLE: 0x53,  # 'S' -- Keyboard_PadTriangle=83
    PadButton.UP: 0x26,  # VK_UP    -- Keyboard_PadUp=265 (GLFW_KEY_UP)
    PadButton.DOWN: 0x28,  # VK_DOWN  -- Keyboard_PadDown=264 (GLFW_KEY_DOWN)
    PadButton.LEFT: 0x25,  # VK_LEFT  -- Keyboard_PadLeft=263 (GLFW_KEY_LEFT)
    PadButton.RIGHT: 0x27,  # VK_RIGHT -- Keyboard_PadRight=262 (GLFW_KEY_RIGHT)
    PadButton.START: 0x0D,  # VK_RETURN -- Keyboard_PadSstart=257 (GLFW_KEY_ENTER)
    PadButton.SELECT: 0x08,  # VK_BACK -- Keyboard_PadSelect=259 (GLFW_KEY_BACKSPACE)
    PadButton.L1: 0x51,  # 'Q' -- Keyboard_PadL1=81
    PadButton.L2: 0x41,  # 'A' -- Keyboard_PadL2=65
    PadButton.L3: 0x57,  # 'W' -- Keyboard_PadL3=87
    PadButton.R1: 0x52,  # 'R' -- Keyboard_PadR1=82
    PadButton.R2: 0x46,  # 'F' -- Keyboard_PadR2=70
    PadButton.R3: 0x54,  # 'T' -- Keyboard_PadR3=84
}

_EXTENDED_KEYS = frozenset({PadButton.UP, PadButton.DOWN, PadButton.LEFT, PadButton.RIGHT})


def _send_key_event(vk: int, key_up: bool, extended: bool) -> None:
    scan = user32.MapVirtualKeyW(vk, 0)
    flags = KEYEVENTF_SCANCODE
    if extended:
        flags |= KEYEVENTF_EXTENDEDKEY
    if key_up:
        flags |= KEYEVENTF_KEYUP
    inp = _INPUT(type=INPUT_KEYBOARD, u=_INPUT_UNION(ki=_KEYBDINPUT(wVk=0, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=None)))
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))


def press_button(button: PadButton, hold_seconds: float = 0.12, vk_map: dict[PadButton, int] = DEFAULT_VK_MAP) -> None:
    """Press and release one button via hardware-level SendInput.
    Caller is responsible for ensuring the target window already has
    real OS focus (see `focus_window`) -- this function does not focus
    anything itself, since focusing is a one-time setup step, not
    something to repeat before every single button press."""
    vk = vk_map[button]
    extended = button in _EXTENDED_KEYS
    _send_key_event(vk, key_up=False, extended=extended)
    time.sleep(hold_seconds)
    _send_key_event(vk, key_up=True, extended=extended)


def find_window_by_process_name(process_name: str) -> int | None:
    """Returns the main window handle of the first running process
    matching `process_name` (e.g. "pcsx-redux.main"), or None. Uses
    EnumWindows rather than a fixed handle, since a window handle is
    only valid for one process lifetime."""
    result: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _callback(hwnd, _lparam):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not user32.IsWindowVisible(hwnd):
            return True
        buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, buf, 512)
        if not buf.value:
            return True
        try:
            import psutil  # only needed for this lookup; the rest of the module has no extra deps

            proc = psutil.Process(pid.value)
            if proc.name().lower() == process_name.lower():
                result.append(hwnd)
                return False
        except Exception:
            pass
        return True

    user32.EnumWindows(_callback, 0)
    return result[0] if result else None


@dataclass
class FocusResult:
    success: bool
    target_hwnd: int


def focus_window(hwnd: int, timeout_seconds: float = 2.0, poll_interval: float = 0.1) -> FocusResult:
    """Give `hwnd` genuine OS-level foreground focus, working around
    Windows' anti-focus-stealing restriction by attaching this
    process's input thread to the current foreground window's thread
    before calling SetForegroundWindow (the standard, documented
    workaround -- SetForegroundWindow alone silently fails when called
    from a process that isn't already the foreground process or
    recently received input). Polls until focus is confirmed rather
    than trusting the return value alone, since the switch can be
    asynchronous."""
    cur_thread = kernel32.GetCurrentThreadId()
    fg_window = user32.GetForegroundWindow()
    fg_thread = user32.GetWindowThreadProcessId(fg_window, None)

    user32.AttachThreadInput(cur_thread, fg_thread, True)
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.BringWindowToTop(hwnd)
    user32.SetForegroundWindow(hwnd)
    user32.AttachThreadInput(cur_thread, fg_thread, False)

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if user32.GetForegroundWindow() == hwnd:
            return FocusResult(success=True, target_hwnd=hwnd)
        time.sleep(poll_interval)
    return FocusResult(success=False, target_hwnd=hwnd)


def move_window_to_primary_monitor(hwnd: int, x: int = 50, y: int = 50, width: int = 800, height: int = 600) -> None:
    """Moves/resizes `hwnd` -- useful when a multi-monitor setup has
    left the target window somewhere input-injection or a human
    observer can't easily reach; found necessary this session when the
    emulator window was on a non-primary monitor."""
    SWP_SHOWWINDOW = 0x0040
    user32.ShowWindow(hwnd, 9)
    user32.SetWindowPos(hwnd, None, x, y, width, height, SWP_SHOWWINDOW)
