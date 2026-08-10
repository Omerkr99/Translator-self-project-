"""Alternative Text Engine, Phase 9 (software-only groundwork): connects
an editor-authored `EditorLayoutPlan` to a live-injectable descriptor
buffer, per the master prompt's Phase 9 instruction: "Connect: editor
layout plan -> binary descriptor -> live injection -> custom renderer."

This module builds the FIRST THREE links of that chain only. The fourth
-- a custom renderer that actually draws glyphs at editor-specified
positions -- is deliberately NOT here. That is the position-override
work explicitly deferred earlier in this project's live-patching work
(see MIPS_PATCH_PLAN.md's Phase 7/8 sections): it needs a multiply to
compute a position-record address and touches globals whose exact
bit-width isn't fully confirmed, and installing it requires its own,
separately-confirmed go-ahead. Nothing in this module writes any MIPS
code, computes any position-record address, or causes the game to draw
a single pixel differently -- it only stages descriptor bytes and a
pointer for the ALREADY-LIVE-CONFIRMED diagnostic-branch stub (Phase 8)
to detect, exactly like this session's own manual test scripts did by
hand. No custom renderer exists yet to act on the positions it carries.

Why this connects through a `PatchProfile` rather than raw addresses:
Phase 7's own history is a direct lesson that a hook site or scratch
region confirmed for one loaded executable/state is not portable to
another (see MIPS_PATCH_PLAN.md's "Phase 7 correction"). Requiring a
`LIVE_CONFIRMED_THIS_SESSION` profile with real `pointer_slot_addr`/
`descriptor_region_addr` values means this module can never silently
inject against an executable nobody has actually verified.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from gcrts.glyph_atlas import GlyphAtlas
from gcrts.layout_descriptor import DescriptorValidationError, encode_layout_descriptor
from gcrts.live_extract import GdbClient
from gcrts.mips_patch_profile import PatchProfile, PatchProfileStatus
from gcrts.render_mode import RenderMode
from gcrts.script_unit import ScriptUnit


@dataclass
class DescriptorInjectionPlan:
    """Everything needed to write one unit's descriptor into a specific,
    live-confirmed profile's memory -- computed with zero emulator
    interaction, so it's fully unit-testable without PCSX-Redux running."""

    unit_id: str
    descriptor_bytes: bytes
    descriptor_addr: int
    pointer_slot_addr: int
    warnings: list[str] = field(default_factory=list)


def build_descriptor_injection_plan(
    unit: ScriptUnit, profile: PatchProfile, atlas: GlyphAtlas | None = None
) -> DescriptorInjectionPlan:
    """Pure function: encode `unit.layout_plan` and package it against
    `profile`'s recorded pointer/descriptor addresses. Refuses (raises
    ValueError) rather than guessing whenever a precondition is missing
    -- an unready unit or an unproven profile should never silently
    produce a plan that looks installable."""
    if unit.render_mode != RenderMode.CUSTOM_ENGINE:
        raise ValueError(f"unit {unit.id!r} is not in CUSTOM_ENGINE render mode (got {unit.render_mode.value!r})")
    if unit.layout_plan is None:
        raise ValueError(f"unit {unit.id!r} has no layout_plan to inject")
    if profile.status != PatchProfileStatus.LIVE_CONFIRMED_THIS_SESSION:
        raise ValueError(
            f"profile {profile.executable_name!r} is not LIVE_CONFIRMED_THIS_SESSION "
            f"(status={profile.status.value!r}) -- refusing to plan an injection against an unproven hook"
        )
    if profile.pointer_slot_addr is None or profile.descriptor_region_addr is None:
        raise ValueError(
            f"profile {profile.executable_name!r} has no pointer_slot_addr/descriptor_region_addr recorded"
        )

    descriptor_bytes = encode_layout_descriptor(unit.layout_plan, atlas=atlas)

    if profile.descriptor_region_size is not None and len(descriptor_bytes) > profile.descriptor_region_size:
        raise DescriptorValidationError(
            f"encoded descriptor is {len(descriptor_bytes)} bytes, exceeding profile "
            f"{profile.executable_name!r}'s reserved descriptor_region_size of {profile.descriptor_region_size}"
        )

    return DescriptorInjectionPlan(
        unit_id=unit.id,
        descriptor_bytes=descriptor_bytes,
        descriptor_addr=profile.descriptor_region_addr,
        pointer_slot_addr=profile.pointer_slot_addr,
    )


@dataclass
class DescriptorInjectionResult:
    success: bool
    error: str | None = None


def inject_descriptor_live(
    plan: DescriptorInjectionPlan, host: str = "127.0.0.1", port: int = 3333
) -> DescriptorInjectionResult:
    """Write the descriptor, then the pointer slot, verifying each write
    by reading it back before proceeding to the next -- the same
    discipline every live write in this project has used since Phase 7.
    Writing the descriptor before the pointer means the pointer can
    never (even momentarily) reference incomplete/unwritten data."""
    client = GdbClient(host=host, port=port, timeout=15)
    try:
        ok_desc = client.write_memory(plan.descriptor_addr, plan.descriptor_bytes)
        rb_desc = client.read_memory(plan.descriptor_addr, len(plan.descriptor_bytes))
        if not ok_desc or rb_desc != plan.descriptor_bytes:
            return DescriptorInjectionResult(success=False, error="descriptor write failed readback verification")

        ptr_bytes = plan.descriptor_addr.to_bytes(4, "little")
        ok_ptr = client.write_memory(plan.pointer_slot_addr, ptr_bytes)
        rb_ptr = client.read_memory(plan.pointer_slot_addr, 4)
        if not ok_ptr or rb_ptr != ptr_bytes:
            return DescriptorInjectionResult(success=False, error="pointer slot write failed readback verification")

        return DescriptorInjectionResult(success=True)
    finally:
        client.close()


def mark_descriptor_injected(unit: ScriptUnit) -> None:
    """Record the milestone on the unit itself, mirroring how
    gcrts.live_injection marks TEXT_BUFFER_INJECTED -- call only after
    inject_descriptor_live() reports success. Deliberately does NOT set
    LIVE_RENDER_VALIDATED (gcrts.render_mode.RuntimePatchStatus) since
    nothing has rendered anything yet -- that milestone belongs to a
    real custom renderer this module doesn't implement."""
    unit.runtime_patch_status.layout_descriptor_injected = True
