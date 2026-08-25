"""Generic emulator-adapter interface for the overlay engine
(`docs/overlay_engine/`).

Per `PS1_Overlay_Runtime_System_Design.md` §4.2/§6, every test/overlay
scenario should be written against this interface, never against
PCSX-Redux directly -- so a future second emulator adapter can be added
without touching overlay/test logic. `PCSXReduxAdapter`
(`gcrts.pcsx_redux_adapter`) is the only implementation today.

Per the same spec's EMU-004 ("if an emulator lacks a capability, the
Toolkit shall degrade gracefully and mark the related validation as
unsupported rather than silently approximating it"), `capabilities()`
must report ONLY what's actually been proven to work for that adapter
-- not what the interface theoretically supports. `PCSXReduxAdapter`
follows this literally: `FRAME_COUNTER` and `AUDIO_CONTROL` are not
advertised because no real endpoint/mechanism for either has been
proven in this project yet (per `docs/status/TOOLKIT_READINESS_AUDIT.md`).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any


class EmulatorCapability(str, Enum):
    MEMORY_READ = "MEMORY_READ"
    MEMORY_WRITE = "MEMORY_WRITE"
    BREAKPOINTS = "BREAKPOINTS"
    SCREENSHOT = "SCREENSHOT"
    SAVE_STATE_LOAD = "SAVE_STATE_LOAD"
    PAUSE_RESUME = "PAUSE_RESUME"
    AUDIO_CONTROL = "AUDIO_CONTROL"
    FRAME_COUNTER = "FRAME_COUNTER"


@dataclass(frozen=True)
class EmulatorCapabilities:
    supported: frozenset[EmulatorCapability]

    def supports(self, capability: EmulatorCapability) -> bool:
        return capability in self.supported

    def require(self, *capabilities: EmulatorCapability) -> "list[EmulatorCapability]":
        """Returns the subset of `capabilities` this adapter does NOT
        support -- an empty list means every requirement is met. A
        caller (e.g. a test scenario) should check this and report
        UNSUPPORTED rather than attempting the action and hoping,
        per EMU-004."""
        return [c for c in capabilities if not self.supports(c)]

    def to_dict(self) -> dict:
        return {"supported": sorted(c.value for c in self.supported)}


class EmulatorAdapter(ABC):
    """Normalized interface for memory, breakpoints, screenshots, save
    states, timing, and (where available) audio controls. Every method
    below corresponds directly to `PS1_Overlay_Runtime_System_Design.md`
    §4.2's pseudocode interface."""

    @abstractmethod
    def capabilities(self) -> EmulatorCapabilities: ...

    @abstractmethod
    def read_memory(self, addr: int, length: int) -> bytes | None: ...

    @abstractmethod
    def write_memory(self, addr: int, data: bytes) -> bool: ...

    @abstractmethod
    def set_breakpoint(self, addr: int) -> bool: ...

    @abstractmethod
    def clear_breakpoint(self, addr: int) -> bool: ...

    @abstractmethod
    def screenshot(self) -> Any: ...

    @abstractmethod
    def load_state(self, slot: int) -> bool: ...

    @abstractmethod
    def pause(self) -> None: ...

    @abstractmethod
    def resume(self) -> None: ...

    def get_frame_counter(self) -> int | None:
        """Default: unsupported. Override only once a real mechanism is
        proven for a given adapter -- never approximate (EMU-004)."""
        return None

    def get_audio_controls(self) -> Any | None:
        """Default: unsupported, for the same reason as
        `get_frame_counter`."""
        return None

    def shutdown(self) -> None:
        """Default no-op; override if the adapter owns a live
        connection/process that needs explicit teardown."""
        return None
