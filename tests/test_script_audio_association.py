import struct

from gcrts.runtime_audio import AudioConfidence, AudioLifecycleState, RuntimeAudioEvent
from gcrts.script_decoder import decode_script
from gcrts.script_audio_association import (
    ScriptAssociationConfidence,
    ScriptAudioAssociation,
    build_script_audio_association,
    capture_script_audio_association,
    find_owning_sound_cue,
    find_owning_unit,
)
from gcrts.script_unit import units_from_script_document

CURSOR_ADDR = 0x800A4CEA
SCRIPT_BUF_ADDR = 0x801FE800


def _pack(words):
    return struct.pack(f"<{len(words)}H", *words)


def _words_one_cue(param=0x007F):
    return [
        0x8900,  # speaker_name_start (family A)
        0x0001,  # char
        0x4800,  # sound_or_voice_cue tag (family B, subtype 0x0800)
        param,  # inline param word
        0x0002,  # char
        0x8500,  # pause_flag_a -> segment break, ends this unit at offset 6
        0xFFFF,  # end marker -> a trailing, separate unit
    ]


def _doc_and_units(words, scene_id="live"):
    doc = decode_script(_pack(words))
    units = units_from_script_document(doc, scene_id, base_ram_address=SCRIPT_BUF_ADDR)
    return doc, units


def _audio_event(source_file="DAT/XA1/XAPACK08.BIN") -> RuntimeAudioEvent:
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


# --- find_owning_sound_cue -------------------------------------------------


def test_find_owning_sound_cue_returns_the_one_before_cursor():
    doc, _ = _doc_and_units(_words_one_cue())
    cue = find_owning_sound_cue(doc, cursor=5)
    assert cue is not None
    assert cue.offset == 2
    assert cue.param == 0x007F


def test_find_owning_sound_cue_none_if_cursor_before_it():
    doc, _ = _doc_and_units(_words_one_cue())
    # cursor=3 is mid-consumption of the 2-word cue (offset 2, ends at 4) -- not yet fully consumed
    assert find_owning_sound_cue(doc, cursor=3) is None


def test_find_owning_sound_cue_picks_the_latest_of_several():
    words = _words_one_cue(param=1)[:-1] + [0x4800, 2, 0x0003, 0x8500, 0xFFFF]  # drop the first list's END marker
    doc, _ = _doc_and_units(words)
    cue = find_owning_sound_cue(doc, cursor=100)
    assert cue.offset == 6  # the second occurrence, not the first
    assert cue.param == 2


# --- find_owning_unit -------------------------------------------------------


def test_find_owning_unit_matches_containing_range():
    _, units = _doc_and_units(_words_one_cue())
    unit = find_owning_unit(units, offset=2)
    assert unit is not None
    assert unit.unit_start_offset <= 2 < unit.unit_end_offset


def test_find_owning_unit_none_outside_any_range():
    _, units = _doc_and_units(_words_one_cue())
    assert find_owning_unit(units, offset=9999) is None


# --- build_script_audio_association -----------------------------------------


def test_build_association_resolves_full_context():
    doc, units = _doc_and_units(_words_one_cue())
    ev = _audio_event()
    assoc = build_script_audio_association(cursor=5, doc=doc, units=units, audio_event=ev, association_id="a1")
    assert assoc.confidence == ScriptAssociationConfidence.SCRIPT_CONTEXT_RESOLVED
    assert assoc.script_unit_id == units[0].id
    assert assoc.control_code_offset == 2
    assert assoc.raw_parameter == 0x007F
    assert assoc.dialogue_text == units[0].original_text
    assert assoc.buffer_fingerprint is not None
    assert assoc.audio_event["source_file"] == "DAT/XA1/XAPACK08.BIN"
    assert assoc.stable_key == f"live_ram/{units[0].id}/offset_0x2/{assoc.buffer_fingerprint}"


def test_build_association_unavailable_without_cursor():
    doc, units = _doc_and_units(_words_one_cue())
    assoc = build_script_audio_association(cursor=None, doc=doc, units=units, audio_event=None, association_id="a1")
    assert assoc.confidence == ScriptAssociationConfidence.UNAVAILABLE
    assert assoc.stable_key is None


def test_build_association_unavailable_without_doc():
    assoc = build_script_audio_association(cursor=5, doc=None, units=[], audio_event=None, association_id="a1")
    assert assoc.confidence == ScriptAssociationConfidence.UNAVAILABLE


def test_build_association_unknown_when_cursor_before_any_cue():
    doc, units = _doc_and_units(_words_one_cue())
    assoc = build_script_audio_association(cursor=1, doc=doc, units=units, audio_event=None, association_id="a1")
    assert assoc.confidence == ScriptAssociationConfidence.SCRIPT_CONTEXT_UNKNOWN
    assert assoc.script_unit_id is None
    assert assoc.stable_key is None


# --- the load-bearing finding: same offset/param, different content, --------
# --- different fingerprint, distinct stable_key -----------------------------


def test_same_offset_and_param_but_different_content_yields_different_fingerprint():
    """Directly encodes this session's live finding: two DIFFERENT
    script buffer loads can both show a sound_or_voice_cue at word
    offset 2 with the same raw parameter, yet be genuinely different
    dialogue lines. buffer_fingerprint (from decoded content, not
    position) must tell them apart."""
    doc_a, units_a = _doc_and_units([0x8900, 0x0001, 0x4800, 0x007F, 0x0002, 0x8500, 0xFFFF])
    doc_b, units_b = _doc_and_units([0x8900, 0x0003, 0x4800, 0x007F, 0x0004, 0x8500, 0xFFFF])

    assoc_a = build_script_audio_association(5, doc_a, units_a, None, "a")
    assoc_b = build_script_audio_association(5, doc_b, units_b, None, "b")

    assert assoc_a.control_code_offset == assoc_b.control_code_offset == 2
    assert assoc_a.raw_parameter == assoc_b.raw_parameter == 0x007F
    assert assoc_a.buffer_fingerprint != assoc_b.buffer_fingerprint
    assert assoc_a.stable_key != assoc_b.stable_key


def test_identical_content_yields_identical_fingerprint():
    words = _words_one_cue()
    doc_a, units_a = _doc_and_units(words)
    doc_b, units_b = _doc_and_units(words)
    assoc_a = build_script_audio_association(5, doc_a, units_a, None, "a")
    assoc_b = build_script_audio_association(5, doc_b, units_b, None, "b")
    assert assoc_a.buffer_fingerprint == assoc_b.buffer_fingerprint


# --- to_dict / from_dict round trip -----------------------------------------


def test_association_round_trips_through_dict():
    doc, units = _doc_and_units(_words_one_cue())
    ev = _audio_event()
    assoc = build_script_audio_association(5, doc, units, ev, "a1")
    restored = ScriptAudioAssociation.from_dict(assoc.to_dict())
    assert restored == assoc


# --- capture_script_audio_association (live-memory-shaped, injected) -------


def _reader(ram: dict):
    return lambda addr, length: ram.get(addr)


def test_capture_reads_cursor_and_buffer_via_injected_memory():
    words = _words_one_cue()
    ram = {
        CURSOR_ADDR: struct.pack("<H", 5),
        SCRIPT_BUF_ADDR: _pack(words) + b"\x00" * 100,
    }
    ev = _audio_event()
    assoc = capture_script_audio_association(_reader(ram), audio_event=ev, association_id="live1")
    assert assoc.confidence == ScriptAssociationConfidence.SCRIPT_CONTEXT_RESOLVED
    assert assoc.raw_parameter == 0x007F
    assert assoc.audio_event["source_file"] == "DAT/XA1/XAPACK08.BIN"


def test_capture_unavailable_when_memory_unreadable():
    assoc = capture_script_audio_association(_reader({}), audio_event=None, association_id="live1")
    assert assoc.confidence == ScriptAssociationConfidence.UNAVAILABLE
