"""Renderer 1 automatic runtime driver, Milestone 1 step 1-3: the profile
data model and live validation layer.

"Renderer 1" is this project's name for the game's OWN native glyph
renderer (not the still-unbuilt gcrts.render_mode.RenderMode.CUSTOM_ENGINE
path). Its full mechanism was mapped and live-proven in
RENDERER_LIVE_PROOF.md sections 10-17: a 14-byte, per-character position
record array is the true source of truth for on-screen glyph placement --

    record_base + i * record_stride   (i = 0..record_count-1)
        +0x0  running per-character counter (index*16)
        +0x2  unused/reserved
        +0x4  font/glyph-set id
        +0x6  clip/scale sentinel
        +0x8  X position (u16)   <- what this driver writes
        +0xa  Y position (u16)   <- what this driver writes
        +0xc  0xffff sentinel/terminator

-- which the renderer copies every frame into a POLY_FT4 primitive and
submits via a single shared `addPrim` entry point. Writing directly to a
record's X/Y is a plain, un-paused memory write (no breakpoint needed):
section 15-17's live tests wrote records while the emulator ran free and
the change was visible on the very next frame, because the renderer
re-reads the record from scratch every cycle.

Why a profile abstraction at all, given this project's own established
lesson (gcrts.mips_patch_profile's docstring) that addresses captured
against one loaded executable/state are not automatically portable to
another: this session re-confirmed that lesson directly. Reading these
exact addresses while PCSX-Redux sat at the title/photo-menu screen
(a different overlay's code entirely) returned bytes that don't decode as
the expected instructions at all; reading them again after loading a
save state that was actually mid-dialogue matched byte-for-byte. A
`Renderer1Profile` is therefore only ever a NAMED HYPOTHESIS for a
specific loaded state, exactly like `PatchProfile` -- `validate_profile()`
below must be called (and must return PROFILE_VALID) before any live
write, never assumed from a prior session's notes.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Callable


class ProfileStatus(Enum):
    UNVERIFIED = "unverified"  # no live confirmation has ever been recorded for this profile
    LIVE_CONFIRMED_THIS_SESSION = "live_confirmed_this_session"  # code fingerprint actually matched live RAM
    STALE_NEEDS_REVERIFICATION = "stale_needs_reverification"  # was confirmed, but a reload/state change may have invalidated it


class ValidationResult(Enum):
    PROFILE_VALID = "profile_valid"  # live fingerprint matches -- safe to read/write against this profile now
    PROFILE_STALE = "profile_stale"  # fingerprint address unreadable (disconnected, unmapped, mid-transition)
    LAYOUT_DRIFT_DETECTED = "layout_drift_detected"  # fingerprint address readable but bytes differ -- a different overlay/state is loaded
    REIDENTIFICATION_REQUIRED = "reidentification_required"  # profile has no fingerprint recorded yet, or was never confirmed


@dataclass
class Renderer1Profile:
    """Everything the driver needs to locate and safely touch one
    loaded state's Renderer 1 position-record array, plus an honest
    record of how much live evidence backs it -- see module docstring."""

    profile_name: str
    status: ProfileStatus = ProfileStatus.UNVERIFIED

    record_base_addr: int | None = None
    record_stride: int = 0x0E
    record_count: int = 14  # confirmed wrap point (RENDERER_LIVE_PROOF.md section 11): the array reuses 14 slots per line
    x_offset: int = 0x8
    y_offset: int = 0xA

    x_load_addr: int | None = None
    x_store_addr: int | None = None
    y_load_addr: int | None = None
    y_store_addr: int | None = None
    addprim_addr: int | None = None

    # A short, stable code snippet read from x_load_addr itself (NOT a
    # data address) -- picked because it is renderer CODE, never touched
    # by this driver's own writes, so validating against it can never be
    # invalidated by the driver's own prior activity.
    code_fingerprint_addr: int | None = None
    code_fingerprint_bytes: bytes | None = None

    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "profile_name": self.profile_name,
            "status": self.status.value,
            "record_base_addr": self.record_base_addr,
            "record_stride": self.record_stride,
            "record_count": self.record_count,
            "x_offset": self.x_offset,
            "y_offset": self.y_offset,
            "x_load_addr": self.x_load_addr,
            "x_store_addr": self.x_store_addr,
            "y_load_addr": self.y_load_addr,
            "y_store_addr": self.y_store_addr,
            "addprim_addr": self.addprim_addr,
            "code_fingerprint_addr": self.code_fingerprint_addr,
            "code_fingerprint_bytes": self.code_fingerprint_bytes.hex() if self.code_fingerprint_bytes else None,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Renderer1Profile":
        return cls(
            profile_name=d["profile_name"],
            status=ProfileStatus(d.get("status", "unverified")),
            record_base_addr=d.get("record_base_addr"),
            record_stride=d.get("record_stride", 0x0E),
            record_count=d.get("record_count", 14),
            x_offset=d.get("x_offset", 0x8),
            y_offset=d.get("y_offset", 0xA),
            x_load_addr=d.get("x_load_addr"),
            x_store_addr=d.get("x_store_addr"),
            y_load_addr=d.get("y_load_addr"),
            y_store_addr=d.get("y_store_addr"),
            addprim_addr=d.get("addprim_addr"),
            code_fingerprint_addr=d.get("code_fingerprint_addr"),
            code_fingerprint_bytes=(
                bytes.fromhex(d["code_fingerprint_bytes"]) if d.get("code_fingerprint_bytes") else None
            ),
            notes=d.get("notes", ""),
        )


def validate_profile(profile: Renderer1Profile, read_memory: Callable[[int, int], bytes | None]) -> ValidationResult:
    """Pure decision function -- `read_memory` is injected so this is
    testable without a live emulator (see tests/test_renderer1_profile.py).

    Never returns PROFILE_VALID for a profile that has no fingerprint
    recorded, no matter what `status` claims -- a status is a claim about
    the PAST, this function's job is to check the PRESENT."""
    if profile.code_fingerprint_addr is None or profile.code_fingerprint_bytes is None:
        return ValidationResult.REIDENTIFICATION_REQUIRED
    if profile.status == ProfileStatus.UNVERIFIED:
        return ValidationResult.REIDENTIFICATION_REQUIRED

    live = read_memory(profile.code_fingerprint_addr, len(profile.code_fingerprint_bytes))
    if live is None:
        return ValidationResult.PROFILE_STALE
    if live != profile.code_fingerprint_bytes:
        return ValidationResult.LAYOUT_DRIFT_DETECTED
    return ValidationResult.PROFILE_VALID


def mark_stale(profile: Renderer1Profile) -> None:
    """Call after any save-state load, reset, or executable transition
    that could have invalidated a previously-confirmed profile -- mirrors
    gcrts.mips_patch_profile.mark_stale for the same reason: a confirmed
    profile must be re-verified live before being trusted again."""
    if profile.status == ProfileStatus.LIVE_CONFIRMED_THIS_SESSION:
        profile.status = ProfileStatus.STALE_NEEDS_REVERIFICATION


def save_registry(profiles: dict[str, Renderer1Profile], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump({name: p.to_dict() for name, p in profiles.items()}, f, indent=2)


def load_registry(path: str) -> dict[str, Renderer1Profile]:
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return {name: Renderer1Profile.from_dict(d) for name, d in raw.items()}


# The one profile this project has actually driven live, end to end, via
# the automatic driver (gcrts.renderer1_runtime) rather than manual GDB
# typing -- see RENDERER_1_RUNTIME_DRIVER.md for the live session that
# captured this exact fingerprint. Everything below is data, not magic:
# a fresh disconnection/relaunch/scene change can and does invalidate it,
# which is exactly what validate_profile() exists to catch.
SLPS00102_BASE_PROFILE = Renderer1Profile(
    profile_name="SLPS00102_base",
    status=ProfileStatus.LIVE_CONFIRMED_THIS_SESSION,
    record_base_addr=0x800A2AD4,
    record_stride=0x0E,
    record_count=14,
    x_offset=0x8,
    y_offset=0xA,
    x_load_addr=0x800397BC,
    x_store_addr=0x800397C4,
    y_load_addr=0x800397C8,
    y_store_addr=0x800397D0,
    addprim_addr=0x800774B4,
    code_fingerprint_addr=0x800397BC,
    code_fingerprint_bytes=bytes.fromhex("0800229600000000080002a60a002296000000000a0002a6"),
    notes=(
        "Fingerprint is the 24-byte lhu/nop/sh/lhu/nop/sh sequence at the shared "
        "X/Y writer (RENDERER_LIVE_PROOF.md section 12). Captured live this "
        "session while a real dialogue scene (SLPS00102.sstate7) was active; "
        "the SAME address range read as unrelated bytes moments earlier while "
        "the title/photo-menu screen was showing -- direct, live evidence that "
        "profile validation against the fingerprint (not just trusting this "
        "constant) is required before every write, not optional caution."
    ),
)
