"""Alternative Text Engine, Phase 1: rendering-mode and runtime-patch-status
models.

Pure data models -- no MIPS patching, no code-cave search, no change to the
proven live-injection path (see BASELINE_REPORT.md for what "proven" means
here and what must keep working unmodified). `RenderMode` is the per-unit
selector the rest of this project's Phase 1+ work hangs off of; the actual
CUSTOM_ENGINE renderer does not exist yet, so selecting it is only ever a
data-model choice at this point, not something that changes behavior.

`RuntimePatchState` exists to give the editor (a later phase) something
concrete to display for "is the engine patch installed yet" without
conflating text-buffer injection (already real, via gcrts.live_injection)
with engine-patch installation (not yet implemented). Keeping these as
separate booleans rather than one combined enum matches the master
prompt's requirement that the editor show them as independent statuses --
a text buffer can be injected while no engine patch exists at all, which a
single "current stage" enum couldn't represent.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RenderMode(Enum):
    """Which rendering path a given ScriptUnit (or a whole scene) should use.

    ORIGINAL      -- game's own data and renderer behavior, untouched.
    HOST_FITTED   -- today's reliable pipeline (gcrts.text_fitting's
                     padding-based word-safe fitting). This is the default
                     for every existing and newly-extracted unit; Phase 1
                     introduces the mode selector without changing what
                     actually renders.
    CUSTOM_ENGINE -- the new editor-controlled layout mechanism described in
                     the master prompt. Selecting this in Phase 1 only
                     records the intent; there is no game-side consumer of
                     it yet (that's Phase 6+ scope: hooking, the layout
                     descriptor, and the MIPS-side dispatcher)."""

    ORIGINAL = "original"
    HOST_FITTED = "host_fitted"
    CUSTOM_ENGINE = "custom_engine"


class RuntimePatchStatus(Enum):
    """The distinct milestones the master prompt's injection-modes section
    asks the editor to track and display separately, not as one collapsed
    "current stage" value -- text injection and engine-patch installation
    are independent activities that can each be true or false on their own."""

    TEXT_BUFFER_READY = "text_buffer_ready"
    TEXT_BUFFER_INJECTED = "text_buffer_injected"
    ENGINE_PATCH_READY = "engine_patch_ready"
    ENGINE_PATCH_INSTALLED = "engine_patch_installed"
    LAYOUT_DESCRIPTOR_INJECTED = "layout_descriptor_injected"
    LIVE_RENDER_VALIDATED = "live_render_validated"


@dataclass
class RuntimePatchState:
    """One boolean per RuntimePatchStatus milestone, so a caller can ask
    "is X true" without needing all-or-nothing enum semantics. All default
    False -- a freshly extracted/loaded unit has none of these yet. Nothing
    in this dataclass performs any GDB/emulator interaction; it is purely a
    record of what a later phase's injector would set, exactly like
    gcrts.editor_state.UnitStatus is a record rather than a mechanism."""

    text_buffer_ready: bool = False
    text_buffer_injected: bool = False
    engine_patch_ready: bool = False
    engine_patch_installed: bool = False
    layout_descriptor_injected: bool = False
    live_render_validated: bool = False

    def to_dict(self) -> dict:
        return {
            "text_buffer_ready": self.text_buffer_ready,
            "text_buffer_injected": self.text_buffer_injected,
            "engine_patch_ready": self.engine_patch_ready,
            "engine_patch_installed": self.engine_patch_installed,
            "layout_descriptor_injected": self.layout_descriptor_injected,
            "live_render_validated": self.live_render_validated,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RuntimePatchState":
        """Every key defaults False if missing, so a dict saved before a
        new milestone existed still loads correctly."""
        return cls(
            text_buffer_ready=bool(d.get("text_buffer_ready", False)),
            text_buffer_injected=bool(d.get("text_buffer_injected", False)),
            engine_patch_ready=bool(d.get("engine_patch_ready", False)),
            engine_patch_installed=bool(d.get("engine_patch_installed", False)),
            layout_descriptor_injected=bool(d.get("layout_descriptor_injected", False)),
            live_render_validated=bool(d.get("live_render_validated", False)),
        )
