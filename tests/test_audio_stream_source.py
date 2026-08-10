import struct

from gcrts.audio_stream_source import (
    STREAM_DESCRIPTOR_PTR_ADDR,
    AudioStreamConfidence,
    AudioStreamSource,
    resolve_audio_stream_source,
)


def _reader(ram: dict):
    return lambda addr, length: ram.get(addr)


def _struct_bytes(params, start_lba, field08, field14):
    return (
        struct.pack("<I", params)
        + struct.pack("<I", start_lba)
        + struct.pack("<I", field08)
        + struct.pack("<I", start_lba)  # duplicate, matches live observation
        + struct.pack("<I", field08)  # duplicate, matches live observation
        + struct.pack("<I", field14)
    )


def _ram_for(descriptor_ptr: int, start_lba: int, field08: int = 0, field14: int = 0) -> dict:
    return {
        STREAM_DESCRIPTOR_PTR_ADDR: struct.pack("<I", descriptor_ptr),
        descriptor_ptr: _struct_bytes(0x007F007F, start_lba, field08, field14),
    }


# --- resolve_audio_stream_source: matches real live-confirmed samples -----


def test_resolve_matches_live_xapack06_sample():
    """Real value read live this session: file_start_lba=116010 exactly
    matches XAPACK06.BIN's own real disc start LBA."""
    ram = _ram_for(0x800A60EC, 116010, field08=120310, field14=131841)
    src = resolve_audio_stream_source(_reader(ram), "s1")
    assert src.descriptor_ptr == 0x800A60EC
    assert src.file_start_lba == 116010
    assert src.file_start_lba_matches_disc is True
    assert src.matched_disc_path == "DAT/XA1/XAPACK06.BIN"
    assert src.confidence == AudioStreamConfidence.LIVE_VERIFIED


def test_resolve_matches_live_xapack08_sample():
    """Real value read live this session: file_start_lba=126218 exactly
    matches XAPACK08.BIN's own real disc start LBA."""
    ram = _ram_for(0x800A60EC, 126218, field08=129542, field14=131841)
    src = resolve_audio_stream_source(_reader(ram), "s2")
    assert src.file_start_lba == 126218
    assert src.matched_disc_path == "DAT/XA1/XAPACK08.BIN"
    assert src.confidence == AudioStreamConfidence.LIVE_VERIFIED


def test_resolve_exposes_but_does_not_overclaim_unconfirmed_fields():
    """field_0x08/field_0x14 are exposed as real observed data but the
    module must never claim their meaning is confirmed."""
    ram = _ram_for(0x800A60EC, 126218, field08=129542, field14=131841)
    src = resolve_audio_stream_source(_reader(ram), "s2")
    assert src.field_0x08_value == 129542
    assert src.field_0x14_value == 131841
    # the field exists and is exposed, but nothing in the model claims
    # to know what it means -- no "event_end_lba" field name is used
    assert not hasattr(src, "event_end_lba")


def test_resolve_unconfirmed_when_lba_is_mid_file_not_a_real_start():
    """A start LBA that lands inside a file (not exactly at its start)
    is NOT silently trusted as a confirmed file-start value."""
    ram = _ram_for(0x800A60EC, 126921, field08=0, field14=0)  # mid-file, per earlier Stage C trace
    src = resolve_audio_stream_source(_reader(ram), "s3")
    assert src.file_start_lba == 126921
    assert src.file_start_lba_matches_disc is False
    assert src.matched_disc_path is None
    assert src.confidence == AudioStreamConfidence.LIVE_OBSERVED_UNCONFIRMED


def test_resolve_unknown_when_descriptor_pointer_unreadable():
    src = resolve_audio_stream_source(_reader({}), "s")
    assert src.confidence == AudioStreamConfidence.UNKNOWN
    assert src.descriptor_ptr is None


def test_resolve_unknown_when_structure_unreadable():
    ram = {STREAM_DESCRIPTOR_PTR_ADDR: struct.pack("<I", 0x800A60EC)}
    src = resolve_audio_stream_source(_reader(ram), "s")
    assert src.descriptor_ptr == 0x800A60EC
    assert src.confidence == AudioStreamConfidence.UNKNOWN


# --- to_dict / from_dict ----------------------------------------------------


def test_round_trips_through_dict():
    ram = _ram_for(0x800A60EC, 126218, field08=129542, field14=131841)
    src = resolve_audio_stream_source(_reader(ram), "s2")
    restored = AudioStreamSource.from_dict(src.to_dict())
    assert restored == src
