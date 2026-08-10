import pytest

from gcrts import layout_descriptor_injection
from gcrts.editor_layout_plan import EditorLayoutPlan, LayoutAlignment, LayoutLine
from gcrts.layout_descriptor import encode_layout_descriptor
from gcrts.layout_descriptor_injection import (
    DescriptorInjectionResult,
    build_descriptor_injection_plan,
    inject_descriptor_live,
    mark_descriptor_injected,
)
from gcrts.mips_patch_profile import PatchProfile, PatchProfileStatus
from gcrts.render_mode import RenderMode
from gcrts.script_unit import ScriptUnit


def _confirmed_profile(**overrides):
    defaults = dict(
        executable_name="UNIDENTIFIED_SESSION_2026-07-27",
        status=PatchProfileStatus.LIVE_CONFIRMED_THIS_SESSION,
        hook_addr=0x8004A378,
        resume_addr=0x8004A380,
        stub_region_addr=0x801AC500,
        stub_region_size=68,
        pointer_slot_addr=0x801AC100,
        descriptor_region_addr=0x801AC600,
        descriptor_region_size=None,
    )
    defaults.update(overrides)
    return PatchProfile(**defaults)


def _unit(render_mode=RenderMode.CUSTOM_ENGINE, layout_plan="default"):
    if layout_plan == "default":
        layout_plan = EditorLayoutPlan(
            unit_id="s_line_00",
            render_mode=RenderMode.CUSTOM_ENGINE,
            language="en",
            source_text="Test",
            edited_text="Test",
            lines=[LayoutLine("Test", 0, 4, 50, 180, LayoutAlignment.LEFT)],
        )
    return ScriptUnit(
        id="s_line_00",
        source="live_ram",
        ram_address=0x801FE800,
        unit_start_offset=0,
        unit_end_offset=4,
        next_unit_start_offset=None,
        raw_codes=[0x0001, 0x0002, 0x0003, 0xFFFF],
        control_events=[],
        original_text="Test",
        edited_text="Test",
        layout_constraints={},
        text_type="dialogue",
        glyphs_used=[1, 2, 3],
        missing_glyphs=[],
        render_mode=render_mode,
        layout_plan=layout_plan,
    )


def test_build_plan_encodes_the_unit_layout_plan_correctly():
    unit = _unit()
    profile = _confirmed_profile()
    plan = build_descriptor_injection_plan(unit, profile)

    assert plan.unit_id == "s_line_00"
    assert plan.descriptor_bytes == encode_layout_descriptor(unit.layout_plan)
    assert plan.descriptor_addr == 0x801AC600
    assert plan.pointer_slot_addr == 0x801AC100


def test_build_plan_refuses_a_non_custom_engine_unit():
    unit = _unit(render_mode=RenderMode.HOST_FITTED)
    profile = _confirmed_profile()
    with pytest.raises(ValueError, match="CUSTOM_ENGINE"):
        build_descriptor_injection_plan(unit, profile)


def test_build_plan_refuses_a_unit_with_no_layout_plan():
    unit = _unit(layout_plan=None)
    profile = _confirmed_profile()
    with pytest.raises(ValueError, match="no layout_plan"):
        build_descriptor_injection_plan(unit, profile)


def test_build_plan_refuses_an_unconfirmed_profile():
    unit = _unit()
    profile = _confirmed_profile(status=PatchProfileStatus.ADDRESSES_HYPOTHESIZED)
    with pytest.raises(ValueError, match="not LIVE_CONFIRMED_THIS_SESSION"):
        build_descriptor_injection_plan(unit, profile)


def test_build_plan_refuses_a_profile_missing_pointer_or_descriptor_addr():
    unit = _unit()
    profile = _confirmed_profile(pointer_slot_addr=None)
    with pytest.raises(ValueError, match="pointer_slot_addr"):
        build_descriptor_injection_plan(unit, profile)


def test_build_plan_refuses_a_descriptor_too_large_for_the_reserved_region():
    unit = _unit()
    profile = _confirmed_profile(descriptor_region_size=4)  # the real descriptor is much bigger than 4 bytes
    with pytest.raises(Exception, match="exceeding profile"):
        build_descriptor_injection_plan(unit, profile)


class _FakeGdbClient:
    """Mirrors gcrts.live_extract.GdbClient's interface without touching
    a socket, matching this project's established pattern (see
    tests/test_live_injection.py) of monkeypatching the exact seam that
    talks to the network."""

    memory: dict[int, bytes] = {}
    fail_addr: int | None = None
    closed = False

    def __init__(self, host="127.0.0.1", port=3333, timeout=30.0):
        pass

    def write_memory(self, addr, data):
        if addr == type(self).fail_addr:
            return False
        type(self).memory[addr] = data
        return True

    def read_memory(self, addr, length):
        return type(self).memory.get(addr, b"")

    def close(self):
        type(self).closed = True


@pytest.fixture(autouse=True)
def _reset_fake_client():
    _FakeGdbClient.memory = {}
    _FakeGdbClient.fail_addr = None
    _FakeGdbClient.closed = False
    yield


def test_inject_descriptor_live_writes_descriptor_then_pointer(monkeypatch):
    monkeypatch.setattr(layout_descriptor_injection, "GdbClient", _FakeGdbClient)
    unit = _unit()
    profile = _confirmed_profile()
    plan = build_descriptor_injection_plan(unit, profile)

    result = inject_descriptor_live(plan)

    assert result == DescriptorInjectionResult(success=True, error=None)
    assert _FakeGdbClient.memory[plan.descriptor_addr] == plan.descriptor_bytes
    assert _FakeGdbClient.memory[plan.pointer_slot_addr] == plan.descriptor_addr.to_bytes(4, "little")
    assert _FakeGdbClient.closed is True


def test_inject_descriptor_live_fails_closed_when_descriptor_write_fails(monkeypatch):
    monkeypatch.setattr(layout_descriptor_injection, "GdbClient", _FakeGdbClient)
    unit = _unit()
    profile = _confirmed_profile()
    plan = build_descriptor_injection_plan(unit, profile)
    _FakeGdbClient.fail_addr = plan.descriptor_addr

    result = inject_descriptor_live(plan)

    assert result.success is False
    assert "descriptor" in result.error
    # the pointer must never be written if the descriptor write itself failed
    assert plan.pointer_slot_addr not in _FakeGdbClient.memory


def test_inject_descriptor_live_fails_closed_when_pointer_write_fails(monkeypatch):
    monkeypatch.setattr(layout_descriptor_injection, "GdbClient", _FakeGdbClient)
    unit = _unit()
    profile = _confirmed_profile()
    plan = build_descriptor_injection_plan(unit, profile)
    _FakeGdbClient.fail_addr = plan.pointer_slot_addr

    result = inject_descriptor_live(plan)

    assert result.success is False
    assert "pointer" in result.error


def test_mark_descriptor_injected_sets_only_that_one_milestone():
    unit = _unit()
    assert unit.runtime_patch_status.layout_descriptor_injected is False

    mark_descriptor_injected(unit)

    assert unit.runtime_patch_status.layout_descriptor_injected is True
    # No custom renderer exists yet, so nothing should claim live rendering was validated.
    assert unit.runtime_patch_status.live_render_validated is False
