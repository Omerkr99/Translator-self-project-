"""Alternative Text Engine, Phase 8: per-executable MIPS patch profiles.

The master prompt asks this phase to "expand to all five narrative call
sites or the proven common caller" and "add executable-specific
profiles." This module provides the data model and the reusable
assembly/install logic; it does NOT claim any executable beyond the one
tested live this session has a working patch. That claim would violate
this project's own "never claim live behavior without live evidence"
rule, and Phase 7's own history is a direct lesson in why: a patch that
looks byte-correct is not the same as a patch confirmed to execute.

Two hard facts driving this design, both learned the hard way during
Phase 7 (see MIPS_PATCH_PLAN.md's "Phase 7 correction" section):

1. **Absolute addresses are not portable across loaded states.** A
   save-state reload showed the exact same conceptual function moved by
   4 bytes and grew a bigger stack frame, and a previously-confirmed
   30KB scratch region was full of unrelated live data afterward. This
   was `MEMORY_MAP_FINDINGS.md`'s "overlay-variance" concern, previously
   flagged but untested -- now directly observed. It means a
   `PatchProfile` is only ever a NAMED HYPOTHESIS for the executable it
   was captured against, never something to install into a different
   overlay just because the design pattern looks the same.
2. **"Game renders fine after patching" is not evidence the hook fired.**
   It's equally consistent with the hook never being reached. The only
   real evidence is a canary/marker write that could not happen any
   other way, checked after live gameplay. Any workflow built on this
   module must keep that discipline -- `status` below distinguishes
   "installed" from "confirmed firing," and only the latter should ever
   be reported to a user as working.

Known executables (from this project's own ISO9660/disassembly findings
in README.md and MEMORY_MAP_FINDINGS.md): `CAP0.EXE` through `CAP4.EXE`,
`CAPX.EXE`, and character-named narrative overlays including `MYOKO.EXE`,
`MRIKA.EXE`, `MNINO.EXE`, `MPRO.EXE`. The master prompt's "five narrative
call sites" most plausibly refers to five character-scenario overlays
(one per playable protagonist) distinct from the CAP0-4/CAPX group --
this project has not independently confirmed there are exactly five, or
which five, so `NARRATIVE_EXECUTABLE_NAMES` below is recorded as
"known so far," not "complete."
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Callable


class PatchProfileStatus(Enum):
    """How much live evidence backs this profile -- never collapse this
    to a single 'installed' boolean, per the Phase 7 lesson above."""

    UNVERIFIED = "unverified"  # no live investigation done for this executable at all
    ADDRESSES_HYPOTHESIZED = "addresses_hypothesized"  # a guess by analogy to a verified profile, not tested
    HOOK_INSTALLED_UNCONFIRMED = "hook_installed_unconfirmed"  # bytes written, canary not yet checked
    LIVE_CONFIRMED_THIS_SESSION = "live_confirmed_this_session"  # a canary/marker actually fired
    STALE_NEEDS_REVERIFICATION = "stale_needs_reverification"  # was confirmed, but state has since reloaded
    CONFIRMED_NOT_FIRING = "confirmed_not_firing"  # installed + actively tested; canary never fired despite
    # confirmed-visible, actively-advancing dialogue -- a genuine negative result, distinct from UNVERIFIED
    # (never tried) or HOOK_INSTALLED_UNCONFIRMED (installed but not yet checked). This is itself valuable
    # evidence: it means the hooked address is very likely not the real call site for THIS executable's
    # rendering, not that something went wrong with the patch.


# Known so far, not claimed complete -- see module docstring.
KNOWN_EXECUTABLE_NAMES: frozenset[str] = frozenset(
    {
        "CAP0.EXE",
        "CAP1.EXE",
        "CAP2.EXE",
        "CAP3.EXE",
        "CAP4.EXE",
        "CAPX.EXE",
        "MYOKO.EXE",
        "MRIKA.EXE",
        "MNINO.EXE",
        "MPRO.EXE",
    }
)

# The subset believed (not independently confirmed) to be the master
# prompt's "five narrative call sites" -- one overlay per playable
# character/scenario, distinct from the CAP0-4/CAPX group. See
# MEMORY_MAP_FINDINGS.md's 13.3 for the reasoning and its caveats.
NARRATIVE_EXECUTABLE_NAMES: frozenset[str] = frozenset({"MYOKO.EXE", "MRIKA.EXE", "MNINO.EXE", "MPRO.EXE"})


@dataclass
class PatchProfile:
    """Everything needed to install and verify one executable's hook,
    plus an honest record of how much of that has actually been done.

    `code_fingerprint` is a short byte snippet read from a stable code
    address (NOT the hook site itself, so patching doesn't invalidate
    its own fingerprint) -- intended for `identify_loaded_executable()`
    to match a live memory image against a known profile before
    installing anything, rather than assuming whichever profile the
    caller happens to pass in is the one actually loaded.
    """

    executable_name: str
    status: PatchProfileStatus = PatchProfileStatus.UNVERIFIED
    hook_addr: int | None = None
    resume_addr: int | None = None
    stub_region_addr: int | None = None
    stub_region_size: int | None = None
    displaced_instruction_bytes: bytes | None = None
    code_fingerprint_addr: int | None = None
    code_fingerprint_bytes: bytes | None = None
    # Where a Phase-9-style descriptor-branch stub reads its pointer from,
    # and where the encoded descriptor bytes themselves should be staged --
    # both live inside stub_region (this session used +0x100/+0x200-style
    # offsets from a scratch base ad hoc; recording them explicitly here is
    # what lets gcrts.layout_descriptor_injection target the right addresses
    # for a given profile instead of assuming a fixed convention).
    pointer_slot_addr: int | None = None
    descriptor_region_addr: int | None = None
    descriptor_region_size: int | None = None
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "executable_name": self.executable_name,
            "status": self.status.value,
            "hook_addr": self.hook_addr,
            "resume_addr": self.resume_addr,
            "stub_region_addr": self.stub_region_addr,
            "stub_region_size": self.stub_region_size,
            "displaced_instruction_bytes": (
                self.displaced_instruction_bytes.hex() if self.displaced_instruction_bytes is not None else None
            ),
            "code_fingerprint_addr": self.code_fingerprint_addr,
            "code_fingerprint_bytes": (
                self.code_fingerprint_bytes.hex() if self.code_fingerprint_bytes is not None else None
            ),
            "pointer_slot_addr": self.pointer_slot_addr,
            "descriptor_region_addr": self.descriptor_region_addr,
            "descriptor_region_size": self.descriptor_region_size,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PatchProfile":
        return cls(
            executable_name=d["executable_name"],
            status=PatchProfileStatus(d.get("status", "unverified")),
            hook_addr=d.get("hook_addr"),
            resume_addr=d.get("resume_addr"),
            stub_region_addr=d.get("stub_region_addr"),
            stub_region_size=d.get("stub_region_size"),
            displaced_instruction_bytes=(
                bytes.fromhex(d["displaced_instruction_bytes"]) if d.get("displaced_instruction_bytes") else None
            ),
            pointer_slot_addr=d.get("pointer_slot_addr"),
            descriptor_region_addr=d.get("descriptor_region_addr"),
            descriptor_region_size=d.get("descriptor_region_size"),
            code_fingerprint_addr=d.get("code_fingerprint_addr"),
            code_fingerprint_bytes=(
                bytes.fromhex(d["code_fingerprint_bytes"]) if d.get("code_fingerprint_bytes") else None
            ),
            notes=d.get("notes", ""),
        )


def new_unverified_registry() -> dict[str, PatchProfile]:
    """One UNVERIFIED profile per known executable name -- the honest
    starting point. Nothing here claims investigation has happened."""
    return {name: PatchProfile(executable_name=name) for name in sorted(KNOWN_EXECUTABLE_NAMES)}


def record_live_confirmation(
    registry: dict[str, PatchProfile],
    executable_name: str,
    *,
    hook_addr: int,
    resume_addr: int,
    stub_region_addr: int,
    stub_region_size: int,
    displaced_instruction_bytes: bytes,
    code_fingerprint_addr: int,
    code_fingerprint_bytes: bytes,
    pointer_slot_addr: int | None = None,
    descriptor_region_addr: int | None = None,
    descriptor_region_size: int | None = None,
    notes: str = "",
) -> PatchProfile:
    """Only call this after a canary/marker has actually been observed
    to flip during live gameplay -- not after a byte-readback check
    alone (Phase 7's mistake). Overwrites any existing entry.

    `pointer_slot_addr`/`descriptor_region_addr` are optional because a
    profile confirmed only up through Phase 8's canary-branch test (no
    real descriptor injection wired up yet) has no occasion to set them
    -- they matter once gcrts.layout_descriptor_injection targets this
    profile for a real Phase 9 injection."""
    profile = PatchProfile(
        executable_name=executable_name,
        status=PatchProfileStatus.LIVE_CONFIRMED_THIS_SESSION,
        hook_addr=hook_addr,
        resume_addr=resume_addr,
        stub_region_addr=stub_region_addr,
        stub_region_size=stub_region_size,
        displaced_instruction_bytes=displaced_instruction_bytes,
        code_fingerprint_addr=code_fingerprint_addr,
        code_fingerprint_bytes=code_fingerprint_bytes,
        pointer_slot_addr=pointer_slot_addr,
        descriptor_region_addr=descriptor_region_addr,
        descriptor_region_size=descriptor_region_size,
        notes=notes,
    )
    registry[executable_name] = profile
    return profile


def record_negative_finding(
    registry: dict[str, PatchProfile],
    executable_name: str,
    *,
    hook_addr: int,
    code_fingerprint_addr: int,
    code_fingerprint_bytes: bytes,
    notes: str,
) -> PatchProfile:
    """Record that a hook was installed and actively tested at
    `hook_addr` -- with dialogue confirmed visible and actively
    advancing throughout the test window -- and its canary never fired.
    This is a genuine, useful result: it means `hook_addr` is very
    likely not the real call site for this executable's live rendering,
    not that the test was inconclusive. `notes` should describe what was
    actually observed (how long polled, what was confirmed intact) so a
    future investigation doesn't have to take the negative result on
    faith. Callers should restore the original bytes at `hook_addr`
    before calling this -- this function only records the finding, it
    does not touch live memory itself."""
    profile = PatchProfile(
        executable_name=executable_name,
        status=PatchProfileStatus.CONFIRMED_NOT_FIRING,
        hook_addr=hook_addr,
        code_fingerprint_addr=code_fingerprint_addr,
        code_fingerprint_bytes=code_fingerprint_bytes,
        notes=notes,
    )
    registry[executable_name] = profile
    return profile


def mark_stale(registry: dict[str, PatchProfile], executable_name: str) -> None:
    """Call after any save-state load or executable reload that could
    have invalidated a previously-confirmed profile -- per this
    session's own direct evidence that reloads shift addresses and
    overwrite scratch regions. A stale profile must be re-verified
    live before being trusted again, never silently re-trusted."""
    profile = registry.get(executable_name)
    if profile is not None and profile.status == PatchProfileStatus.LIVE_CONFIRMED_THIS_SESSION:
        profile.status = PatchProfileStatus.STALE_NEEDS_REVERIFICATION


def hypothesize_from_verified(
    registry: dict[str, PatchProfile],
    verified_name: str,
    target_name: str,
    *,
    address_delta: int = 0,
) -> PatchProfile:
    """Build an UNTESTED guess for `target_name` by analogy to a
    LIVE_CONFIRMED profile, shifting every address by `address_delta`
    (the exact kind of shift this session observed -- e.g. the +4 seen
    between two loaded states of what was structurally the same
    function). This is explicitly a hypothesis, never installed without
    live verification -- status is ADDRESSES_HYPOTHESIZED, not
    confirmed, and callers must not treat it as safe to use blind."""
    verified = registry.get(verified_name)
    if verified is None or verified.status != PatchProfileStatus.LIVE_CONFIRMED_THIS_SESSION:
        raise ValueError(f"{verified_name!r} is not a live-confirmed profile to hypothesize from")

    def shift(addr: int | None) -> int | None:
        return addr + address_delta if addr is not None else None

    profile = PatchProfile(
        executable_name=target_name,
        status=PatchProfileStatus.ADDRESSES_HYPOTHESIZED,
        hook_addr=shift(verified.hook_addr),
        resume_addr=shift(verified.resume_addr),
        stub_region_addr=verified.stub_region_addr,  # scratch region is NOT assumed portable at all -- must be re-scanned
        stub_region_size=None,
        displaced_instruction_bytes=verified.displaced_instruction_bytes,
        code_fingerprint_addr=shift(verified.code_fingerprint_addr),
        code_fingerprint_bytes=None,  # must be re-captured live, never copied from a different executable
        notes=(
            f"Hypothesized from {verified_name!r} by a {address_delta:+d}-byte address shift. "
            "UNTESTED -- the scratch region and fingerprint bytes are explicitly NOT copied "
            "(this session directly observed a previously-safe scratch region become fully "
            "occupied after a reload, and a shifted function gain extra saved registers -- "
            "analogy is a starting point for investigation, never a substitute for it)."
        ),
    )
    registry[target_name] = profile
    return profile


def identify_loaded_executable(
    registry: dict[str, PatchProfile], read_memory: Callable[[int, int], bytes | None]
) -> str | None:
    """Match the live memory image against every profile with a
    recorded fingerprint, returning the executable name on a match or
    None if nothing matches (including the honest case where every
    profile is still UNVERIFIED and has no fingerprint to check).
    `read_memory` is injected rather than importing GdbClient directly,
    so this stays testable without a live emulator."""
    for name, profile in registry.items():
        if profile.code_fingerprint_addr is None or profile.code_fingerprint_bytes is None:
            continue
        live = read_memory(profile.code_fingerprint_addr, len(profile.code_fingerprint_bytes))
        if live == profile.code_fingerprint_bytes:
            return name
    return None


def save_registry(registry: dict[str, PatchProfile], path: str) -> None:
    """Persist the registry as JSON so a confirmed profile survives
    between sessions -- otherwise every restart would have to re-derive
    live evidence from scratch, or worse, tempt reuse of a stale
    in-memory assumption. Callers are still responsible for calling
    `mark_stale()` on anything that might have been invalidated by a
    reload before relying on what this file says."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump({name: profile.to_dict() for name, profile in registry.items()}, f, indent=2)


def load_registry(path: str) -> dict[str, PatchProfile]:
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return {name: PatchProfile.from_dict(d) for name, d in raw.items()}


def coverage_report(registry: dict[str, PatchProfile]) -> list[dict]:
    """One row per known executable: name, status, and whether it's the
    narrative-call-site subset the master prompt specifically asks
    Phase 8 to expand across. Mirrors gcrts.render_paths.coverage_report's
    shape for the same honest-inventory purpose."""
    rows = []
    for name in sorted(KNOWN_EXECUTABLE_NAMES):
        profile = registry.get(name)
        status = profile.status.value if profile is not None else PatchProfileStatus.UNVERIFIED.value
        rows.append(
            {
                "executable_name": name,
                "status": status,
                "is_narrative_call_site": name in NARRATIVE_EXECUTABLE_NAMES,
            }
        )
    return rows
