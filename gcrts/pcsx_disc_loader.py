"""Robust automation for PCSX-Redux's File > Open Disk Image flow --
built to replace this project's earlier, repeated pattern of guessing
pixel coordinates for a specific file's row (fragile: the row position
depends on how many files exist and their alphabetical order, and had
to be re-derived by hand nearly every time a new disc was loaded this
session).

**Two real findings this required, both load-bearing:**

1. **"Open Disk Image" is a real, separate, title-searchable native
   top-level window** (class `GLFW30`), not content drawn inside the
   main window as originally assumed -- `EnumWindows` scoped to the
   PCSX-Redux process's PID(s) with an exact title match reliably finds
   it, and its own `GetWindowRect` should be used for all coordinate
   math (never assumed relative to the main window: this dialog's
   on-screen position is independent of the main window's, it does not
   recenter itself around a moved/resized main window).

2. **Synthetic keyboard text input does not work on this dialog.**
   Both `SendInput` with `KEYEVENTF_UNICODE` (character text) and a
   plain `VK_BACK` key (backspace) were tested directly against the
   real, focused "File name" field and had zero observable effect,
   even though `SetForegroundWindow`/focus succeeded and mouse clicks
   on the exact same window work perfectly and reliably (confirmed:
   clicking a file row both highlights it AND auto-populates "File
   name"). This is consistent with `gcrts.pcsx_keyboard_input`'s own
   documented finding that this game/engine's GLFW input handling
   doesn't uniformly accept every synthetic input path -- there, only
   `SendInput` with real scancodes (not `PostMessage`/`SendKeys`)
   reached the emulated pad; here, apparently *no* tested synthetic
   keyboard path reaches this particular ImGui text widget, only
   mouse clicks do. **Do not try to type a filename into this dialog.**

Given (2), the only reliable way to pick a specific file is to click
its exact row -- so this module computes that row's pixel position
from the real directory listing (sorted the same case-insensitive way
the dialog itself sorts, confirmed empirically against a real listing
of 10 files) rather than a hand-counted, hardcoded offset that breaks
the moment the directory's contents change.
"""
from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes
from dataclasses import dataclass

import psutil

user32 = ctypes.windll.user32

# Pixel geometry of the "Open Disk Image" dialog's file list, measured
# directly against a real 600x400 capture of the dialog this session:
# selecting the 4th file in a real 10-file listing highlighted a band
# from y=151 to y=170 (20px tall), giving row 0's center at y=101 and
# each subsequent row 20px below the last.
FIRST_ROW_CENTER_Y = 101
ROW_HEIGHT = 20
NAME_COLUMN_X = 200
OPEN_BUTTON_POS = (445, 380)

FILE_MENU_POS = (29, 42)
OPEN_DISK_IMAGE_MENU_ITEM_POS = (66, 69)

DIALOG_TITLE = "Open Disk Image"


def _click(x: int, y: int, hold_seconds: float = 0.05, settle_seconds: float = 0.2) -> None:
    user32.SetCursorPos(x, y)
    time.sleep(hold_seconds)
    user32.mouse_event(0x0002, 0, 0, 0, 0)  # MOUSEEVENTF_LEFTDOWN
    time.sleep(hold_seconds)
    user32.mouse_event(0x0004, 0, 0, 0, 0)  # MOUSEEVENTF_LEFTUP
    time.sleep(settle_seconds)


def _window_rect(hwnd: int) -> tuple[int, int, int, int]:
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom


def _pids_for_process_name(process_name: str) -> set[int]:
    return {p.info["pid"] for p in psutil.process_iter(["pid", "name"]) if (p.info["name"] or "").lower() == process_name.lower()}


def find_window_by_exact_title(title: str, process_name: str | None = None) -> int | None:
    """Like `gcrts.pcsx_keyboard_input.find_window_by_process_name` but
    matches an exact window TITLE instead of "first visible window
    owned by this process" -- needed because a process can own several
    top-level windows at once (the main window and this dialog both
    belong to the same PID) and only an exact title reliably picks out
    one specific window among them."""
    target_pids = _pids_for_process_name(process_name) if process_name else None
    result: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        if target_pids is not None:
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value not in target_pids:
                return True
        buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, buf, 512)
        if buf.value == title:
            result.append(hwnd)
            return False
        return True

    user32.EnumWindows(_callback, 0)
    return result[0] if result else None


def wait_for_window_by_exact_title(title: str, process_name: str | None = None, timeout: float = 5.0, poll_interval: float = 0.15) -> int | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        hwnd = find_window_by_exact_title(title, process_name)
        if hwnd is not None:
            return hwnd
        time.sleep(poll_interval)
    return None


def _row_index_for_filename(game_dir: str, filename: str) -> int:
    """Reproduces the dialog's own file ordering (case-insensitive
    alphabetical -- confirmed against a real 10-file listing) from the
    actual directory contents, so the row position is derived from
    real, current disk state rather than a hardcoded guess that goes
    stale the moment a file is added, removed, or renamed."""
    entries = sorted(os.listdir(game_dir), key=str.lower)
    return entries.index(filename)


@dataclass
class DiscLoadResult:
    success: bool
    row_index: int
    dialog_hwnd: int


def open_disk_image(
    main_window_hwnd: int,
    filename: str,
    game_dir: str = r"C:\PCSXRedux\game",
    process_name: str = "pcsx-redux.main",
    dialog_timeout: float = 5.0,
) -> DiscLoadResult:
    """Loads `filename` (must already exist in `game_dir`) via File >
    Open Disk Image, clicking its exact row rather than typing its name
    (see module docstring for why typing doesn't work here). Returns
    once the "Open" click has been sent; callers should confirm the
    load themselves via the log panel or GAME ID, the same way every
    other live check in this project verifies rather than assumes."""
    main_rect = _window_rect(main_window_hwnd)
    _click(main_rect[0] + FILE_MENU_POS[0], main_rect[1] + FILE_MENU_POS[1])
    _click(main_rect[0] + OPEN_DISK_IMAGE_MENU_ITEM_POS[0], main_rect[1] + OPEN_DISK_IMAGE_MENU_ITEM_POS[1])

    dialog_hwnd = wait_for_window_by_exact_title(DIALOG_TITLE, process_name, timeout=dialog_timeout)
    if dialog_hwnd is None:
        return DiscLoadResult(success=False, row_index=-1, dialog_hwnd=-1)

    row_index = _row_index_for_filename(game_dir, filename)
    dialog_rect = _window_rect(dialog_hwnd)
    row_y = FIRST_ROW_CENTER_Y + row_index * ROW_HEIGHT
    _click(dialog_rect[0] + NAME_COLUMN_X, dialog_rect[1] + row_y)
    _click(dialog_rect[0] + OPEN_BUTTON_POS[0], dialog_rect[1] + OPEN_BUTTON_POS[1])

    return DiscLoadResult(success=True, row_index=row_index, dialog_hwnd=dialog_hwnd)
