"""ExternalOverlayRenderer: a real transparent, always-on-top desktop
window for the overlay engine's external (host-side) backend
(`docs/overlay_engine/PS1_OVERLAY_RUNTIME_SYSTEM_DESIGN.md` §4.1,
EXT-003).

Deliberately scoped for this stage: shows a single text message,
always-on-top, semi-transparent, positioned in a configurable screen
location. It does NOT track the emulator window's exact bounds yet
(SDD's "aligned to emulator output" is aspirational for a later pass
-- this stage proves the render/timing/evidence loop, not perfect
alignment). Never blocks with `mainloop()`: `pump()` processes pending
Tk events in small increments so a caller (the `LiveTestRunner`) can
interleave screenshot capture and emulator polling during the display
window, rather than the overlay owning the whole event loop.

This module cannot be meaningfully unit-tested without a real display
-- Tk window creation and rendering are inherently a manual/live-
verification concern, matching this project's own established pattern
for its existing Tk tools (`asset_inspector_ui.py`,
`visual_inspector_ui.py`): backend logic gets tests, GUI wiring gets
live verification. `gcrts.live_test_runner` is written against a
small duck-typed interface (`show`/`pump`/`hide`) precisely so its own
orchestration logic (timing, evidence-bundle construction) CAN be
fully tested with a fake renderer, without ever opening a real window
in automated tests.
"""
from __future__ import annotations

import tkinter as tk


class ExternalOverlayRenderer:
    def __init__(
        self,
        font_size: int = 28,
        fg: str = "white",
        bg: str = "black",
        alpha: float = 0.85,
        position: tuple[int, int] = (100, 100),
    ):
        self.font_size = font_size
        self.fg = fg
        self.bg = bg
        self.alpha = alpha
        self.position = position
        self._root: tk.Tk | None = None
        self._label: tk.Label | None = None

    @property
    def is_visible(self) -> bool:
        return self._root is not None

    def show(self, text: str) -> None:
        """Create and display the overlay window immediately with the
        given text. Non-blocking -- returns as soon as the window is
        drawn once. Calling this while already visible replaces the
        displayed text without flashing a new window."""
        if self._root is not None and self._label is not None:
            self._label.config(text=text)
            self._root.update()
            return

        self._root = tk.Tk()
        self._root.overrideredirect(True)
        self._root.attributes("-topmost", True)
        try:
            self._root.attributes("-alpha", self.alpha)
        except tk.TclError:
            pass  # some platforms/window managers don't support per-window alpha; degrade to opaque
        self._label = tk.Label(
            self._root, text=text, font=("Segoe UI", self.font_size, "bold"), fg=self.fg, bg=self.bg, padx=20, pady=12
        )
        self._label.pack()
        x, y = self.position
        self._root.geometry(f"+{x}+{y}")
        self._root.update_idletasks()
        self._root.update()

    def pump(self) -> None:
        """Process pending Tk events without blocking. Call in a loop
        while the overlay should remain visible/responsive; a no-op if
        nothing is currently shown."""
        if self._root is not None:
            self._root.update()

    def hide(self) -> None:
        if self._root is not None:
            self._root.destroy()
            self._root = None
            self._label = None
