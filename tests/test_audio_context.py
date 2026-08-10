import struct

from gcrts.audio_context import (
    TABLE1_BASE,
    TABLE2_BASE,
    AudioContext,
    AudioContextConfidence,
    audio_context_for_association,
    cross_validate_source,
    resolve_audio_context,
)
from gcrts.runtime_audio import AudioConfidence, AudioLifecycleState, RuntimeAudioEvent
from gcrts.script_audio_association import ScriptAssociationConfidence, ScriptAudioAssociation


def _reader(ram: dict):
    return lambda addr, length: ram.get(addr)


def _string_bytes(name: str) -> bytes:
    return name.encode("ascii") + b"\x00" * (12 - len(name))


def _ram_for(selector: int, xapack_number: int, string_addr: int, filename: str) -> dict:
    return {
        TABLE1_BASE + selector * 5: bytes([xapack_number]),
        TABLE2_BASE + xapack_number * 4: struct.pack("<I", string_addr),
        string_addr: _string_bytes(filename),
    }


# --- resolve_audio_context, matching the real live-confirmed samples ------


def test_resolve_audio_context_matches_live_selector_25_sample():
    """Real values read live this session: selector 25 -> table1 value 8
    -> string pointer 0x80046c20 -> "XAPACK08"."""
    ram = _ram_for(25, 8, 0x80046C20, "XAPACK08")
    ctx = resolve_audio_context(_reader(ram), selector_value=25, context_id="c1")
    assert ctx.selector_value == 25
    assert ctx.table1_value == 8
    assert ctx.string_ptr == 0x80046C20
    assert ctx.resolved_filename == "XAPACK08"
    assert ctx.confidence == AudioContextConfidence.LIVE_VERIFIED


def test_resolve_audio_context_matches_live_selector_26_sample():
    """Real values read live this session: selector 26 -> table1 value 6
    -> string pointer 0x80046c38 -> "XAPACK06"."""
    ram = _ram_for(26, 6, 0x80046C38, "XAPACK06")
    ctx = resolve_audio_context(_reader(ram), selector_value=26, context_id="c2")
    assert ctx.selector_value == 26
    assert ctx.table1_value == 6
    assert ctx.string_ptr == 0x80046C38
    assert ctx.resolved_filename == "XAPACK06"
    assert ctx.confidence == AudioContextConfidence.LIVE_VERIFIED


def test_resolve_audio_context_different_selectors_yield_different_filenames():
    """The core validated claim: two different selectors resolve to two
    different physical filenames -- this is what actually explains why
    the same script parameter (127) produced two different XAPACK
    files."""
    ram = {**_ram_for(25, 8, 0x80046C20, "XAPACK08"), **_ram_for(26, 6, 0x80046C38, "XAPACK06")}
    ctx_a = resolve_audio_context(_reader(ram), 25, "a")
    ctx_b = resolve_audio_context(_reader(ram), 26, "b")
    assert ctx_a.resolved_filename != ctx_b.resolved_filename
    assert ctx_a.resolved_filename == "XAPACK08"
    assert ctx_b.resolved_filename == "XAPACK06"


def test_resolve_audio_context_all_nine_valid_xapack_numbers():
    """Live-confirmed this session for ALL 9 possible table1 values
    (0-8), not just the two observed selectors -- table1_value IS the
    XAPACK file number directly."""
    ram = {}
    for n in range(9):
        ram.update(_ram_for(100 + n, n, 0x80046C20 + (8 - n) * 12, f"XAPACK0{n}"))
    for n in range(9):
        ctx = resolve_audio_context(_reader(ram), 100 + n, f"c{n}")
        assert ctx.resolved_filename == f"XAPACK0{n}"
        assert ctx.confidence == AudioContextConfidence.LIVE_VERIFIED


# --- scope-limit handling: resolved strings that aren't real disc files ---


def test_resolve_audio_context_partial_when_resolved_name_is_not_a_real_disc_file():
    """A resolved string that LOOKS like a valid filename but doesn't
    match any of the disc's real 43 XAPACK files is not silently
    trusted -- see module docstring: live memory past the real table
    extent (index 42) was found to keep producing exactly this kind of
    plausible-but-fake text ("XAPACK43", "XAPACK44", ...)."""
    ram = _ram_for(7, 99, 0x80046C20, "XAPACK99")  # no real disc file named XAPACK99
    ctx = resolve_audio_context(_reader(ram), selector_value=7, context_id="c")
    assert ctx.table1_value == 99
    assert ctx.resolved_filename == "XAPACK99"
    assert ctx.resolved_disc_path is None
    assert ctx.confidence == AudioContextConfidence.LIVE_VERIFIED_PARTIAL


def test_resolve_audio_context_valid_for_a_previously_undertested_high_index():
    """Regression for a real bug caught live this session: an earlier
    version of this module hard-capped table1_value at 8 and wrongly
    reported a real, valid selector (resolving to XAPACK09, a genuine
    disc file) as unresolved. XAPACK09-42 must all resolve correctly."""
    ram = _ram_for(50, 9, 0x80046C14, "XAPACK09")
    ctx = resolve_audio_context(_reader(ram), selector_value=50, context_id="c")
    assert ctx.resolved_filename == "XAPACK09"
    assert ctx.resolved_disc_path == "DAT/XA1/XAPACK09.BIN"
    assert ctx.confidence == AudioContextConfidence.LIVE_VERIFIED


def test_resolve_audio_context_unknown_without_selector():
    ctx = resolve_audio_context(_reader({}), selector_value=None, context_id="c")
    assert ctx.confidence == AudioContextConfidence.UNKNOWN
    assert ctx.table1_value is None


def test_resolve_audio_context_unknown_when_table1_unreadable():
    ctx = resolve_audio_context(_reader({}), selector_value=25, context_id="c")
    assert ctx.confidence == AudioContextConfidence.UNKNOWN
    assert ctx.table1_entry_addr == TABLE1_BASE + 25 * 5


def test_resolve_audio_context_unknown_when_table2_unreadable():
    ram = {TABLE1_BASE + 25 * 5: bytes([8])}  # table1 readable, table2 is not
    ctx = resolve_audio_context(_reader(ram), selector_value=25, context_id="c")
    assert ctx.table1_value == 8
    assert ctx.string_ptr is None
    assert ctx.confidence == AudioContextConfidence.UNKNOWN


def test_resolve_audio_context_partial_when_string_unreadable():
    ram = {
        TABLE1_BASE + 25 * 5: bytes([8]),
        TABLE2_BASE + 8 * 4: struct.pack("<I", 0x80046C20),
        # string bytes at 0x80046c20 deliberately absent
    }
    ctx = resolve_audio_context(_reader(ram), selector_value=25, context_id="c")
    assert ctx.string_ptr == 0x80046C20
    assert ctx.resolved_filename is None
    assert ctx.confidence == AudioContextConfidence.LIVE_VERIFIED_PARTIAL


# --- to_dict / from_dict ----------------------------------------------------


def test_audio_context_round_trips_through_dict():
    ram = _ram_for(25, 8, 0x80046C20, "XAPACK08")
    ctx = resolve_audio_context(_reader(ram), 25, "c1")
    restored = AudioContext.from_dict(ctx.to_dict())
    assert restored == ctx


# --- audio_context_for_association ------------------------------------------


def _association(control_code_raw_low_byte, confidence=ScriptAssociationConfidence.SCRIPT_CONTEXT_RESOLVED) -> ScriptAudioAssociation:
    return ScriptAudioAssociation(
        association_id="a",
        script_source="live_ram",
        script_unit_id="live_line_00",
        script_unit_start=0,
        script_unit_end=10,
        script_cursor=5,
        control_code_offset=1,
        control_code_type=0x0800,
        control_code_raw_low_byte=control_code_raw_low_byte,
        raw_parameter=127,
        dialogue_text="hello",
        buffer_fingerprint="abc123",
        audio_event=None,
        confidence=confidence,
    )


def test_audio_context_for_association_uses_the_associations_selector():
    ram = _ram_for(25, 8, 0x80046C20, "XAPACK08")
    assoc = _association(25)
    ctx = audio_context_for_association(_reader(ram), assoc, "c1")
    assert ctx.selector_value == 25
    assert ctx.resolved_filename == "XAPACK08"


def test_audio_context_for_association_unknown_when_association_unresolved():
    assoc = _association(25, confidence=ScriptAssociationConfidence.SCRIPT_CONTEXT_UNKNOWN)
    ctx = audio_context_for_association(_reader({}), assoc, "c1")
    assert ctx.confidence == AudioContextConfidence.UNKNOWN


def test_audio_context_for_association_unknown_when_association_none():
    ctx = audio_context_for_association(_reader({}), None, "c1")
    assert ctx.confidence == AudioContextConfidence.UNKNOWN


# --- cross_validate_source: the two independent resolution paths agree ----


def _event(source_file: str) -> RuntimeAudioEvent:
    return RuntimeAudioEvent(
        event_id="e",
        source_type="voice",
        script_parameter=127,
        audio_category=2,
        source_file=source_file,
        xa_channel=None,
        start_lba=126921,
        resolution_method="live_lba",
        position_counter=126921,
        position_counter_start=126921,
        playback_offset_ms=None,
        state=AudioLifecycleState.PLAYING,
        confidence=AudioConfidence.LIVE_LBA_RESOLVED,
    )


def test_cross_validate_source_true_when_independent_paths_agree():
    """Live-confirmed this session: the LBA-based resolver
    (gcrts.runtime_audio) and the selector-table resolver
    (gcrts.audio_context) independently landed on the same file."""
    event = _event("DAT/XA1/XAPACK08.BIN")
    context = resolve_audio_context(_reader(_ram_for(25, 8, 0x80046C20, "XAPACK08")), 25, "c")
    assert cross_validate_source(event, context) is True


def test_cross_validate_source_false_when_independent_paths_disagree():
    event = _event("DAT/XA1/XAPACK06.BIN")
    context = resolve_audio_context(_reader(_ram_for(25, 8, 0x80046C20, "XAPACK08")), 25, "c")
    assert cross_validate_source(event, context) is False


def test_cross_validate_source_none_without_both_signals():
    context = resolve_audio_context(_reader(_ram_for(25, 8, 0x80046C20, "XAPACK08")), 25, "c")
    assert cross_validate_source(None, context) is None
    assert cross_validate_source(_event("DAT/XA1/XAPACK08.BIN"), None) is None
    unresolved_ctx = resolve_audio_context(_reader({}), None, "c")
    assert cross_validate_source(_event("DAT/XA1/XAPACK08.BIN"), unresolved_ctx) is None
