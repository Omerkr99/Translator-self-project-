import pytest

from gcrts.spu_playback_trace import (
    CdCommandEvent,
    HeartbeatEvent,
    MarkEvent,
    SaveStateLoadedEvent,
    SpuKeyWriteEvent,
    SpucntWriteEvent,
    TraceEventType,
    UnknownTraceEventError,
    VOICE_BLOCK_SIZE,
    VOICE_COUNT,
    cdrom_command_name,
    decode_voice_mask,
    load_trace,
    merge_traces,
    parse_jsonl_line,
    voice_register_address,
    write_event,
)
from gcrts.spu_audio_path import SPU_BASE_VALUE, OFFSET_MAIN_VOL_L


# --- decode_voice_mask -------------------------------------------------------


def test_decode_voice_mask_empty():
    assert decode_voice_mask(0) == []


def test_decode_voice_mask_single_voice():
    assert decode_voice_mask(1 << 5) == [5]


def test_decode_voice_mask_multiple_voices():
    assert decode_voice_mask((1 << 0) | (1 << 7) | (1 << 23)) == [0, 7, 23]


def test_decode_voice_mask_all_voices():
    full_mask = (1 << VOICE_COUNT) - 1
    assert decode_voice_mask(full_mask) == list(range(VOICE_COUNT))


# --- voice_register_address ---------------------------------------------------


def test_voice_register_address_voice_0():
    assert voice_register_address(0, 0x04) == SPU_BASE_VALUE + 0x04


def test_voice_register_address_voice_5():
    assert voice_register_address(5, 0x06) == SPU_BASE_VALUE + 5 * VOICE_BLOCK_SIZE + 0x06


def test_voice_register_address_rejects_out_of_range():
    with pytest.raises(ValueError):
        voice_register_address(24, 0x00)
    with pytest.raises(ValueError):
        voice_register_address(-1, 0x00)


def test_voice_block_layout_matches_already_verified_control_registers():
    """Cross-check: 24 voices * 16 bytes must land exactly where this
    project's own already-verified OFFSET_MAIN_VOL_L begins -- if
    either constant were wrong, this equality would break."""
    assert VOICE_COUNT * VOICE_BLOCK_SIZE == OFFSET_MAIN_VOL_L


# --- SpuKeyWriteEvent ----------------------------------------------------------


def test_spu_key_write_event_is_meaningful_false_for_zero_mask():
    e = SpuKeyWriteEvent(t=1.0, write_pc=0x800866A8, family="PERIODIC_VOICE_SYNC", register="KEY_ON", voice_mask=0)
    assert e.is_meaningful is False
    assert e.active_voices == []


def test_spu_key_write_event_is_meaningful_true_for_nonzero_mask():
    e = SpuKeyWriteEvent(t=1.0, write_pc=0x800866A8, family="PERIODIC_VOICE_SYNC", register="KEY_ON", voice_mask=0x4)
    assert e.is_meaningful is True
    assert e.active_voices == [2]


# --- JSONL round trip ----------------------------------------------------------


def test_write_and_parse_spu_key_write_event_round_trips(tmp_path):
    path = str(tmp_path / "trace.jsonl")
    e = SpuKeyWriteEvent(t=1.5, write_pc=0x800866A8, family="PERIODIC_VOICE_SYNC", register="KEY_ON", voice_mask=3, cpu_pc=0x80086650, frame=42)
    with open(path, "w", encoding="utf-8") as f:
        write_event(e, f)
    loaded = load_trace(path)
    assert len(loaded) == 1
    assert loaded[0] == e


def test_write_and_parse_all_event_types_round_trip(tmp_path):
    path = str(tmp_path / "trace.jsonl")
    events = [
        SpuKeyWriteEvent(t=0.0, write_pc=0x800866A8, family="PERIODIC_VOICE_SYNC", register="KEY_ON", voice_mask=0),
        SpucntWriteEvent(t=0.1, write_pc=0x80081BB8, value=0xC001),
        CdCommandEvent(t=0.15, call_site_addr=0x8008182C, command_byte=0x0D, a0=2, a1=0x800A3070),
        HeartbeatEvent(t=0.2, position_counter=126921, lifecycle_state_raw=1, last_req_params=127),
        SaveStateLoadedEvent(t=0.0, hard=False),
        MarkEvent(t=5.0, label="target line heard"),
    ]
    with open(path, "w", encoding="utf-8") as f:
        for e in events:
            write_event(e, f)
    loaded = load_trace(path)
    assert loaded == events


def test_load_trace_skips_blank_lines(tmp_path):
    path = str(tmp_path / "trace.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        write_event(MarkEvent(t=1.0), f)
        f.write("\n")
        write_event(MarkEvent(t=2.0), f)
        f.write("\n\n")
    assert len(load_trace(path)) == 2


def test_parse_jsonl_line_unknown_event_raises():
    with pytest.raises(UnknownTraceEventError):
        parse_jsonl_line('{"event": "NOT_A_REAL_EVENT", "t": 1.0}')


def test_spucnt_write_event_cd_audio_enable_bit():
    e = SpucntWriteEvent(t=0.0, write_pc=0x80081BB8, value=0xC001)
    assert e.cd_audio_enable_bit_set is True
    e2 = SpucntWriteEvent(t=0.0, write_pc=0x80081BB8, value=0xC000)
    assert e2.cd_audio_enable_bit_set is False


# --- CdCommandEvent / cdrom_command_name ----------------------------------------


def test_cdrom_command_name_known_bytes():
    assert cdrom_command_name(0x0D) == "Setfilter"
    assert cdrom_command_name(0x0E) == "Setmode"
    assert cdrom_command_name(0x06) == "ReadN"
    assert cdrom_command_name(0x11) == "GetlocP"


def test_cdrom_command_name_unknown_byte():
    assert cdrom_command_name(0xFF) == "UNKNOWN(0xFF)"


def test_cd_command_event_command_name_property():
    e = CdCommandEvent(t=1.0, call_site_addr=0x8008182C, command_byte=0x0D, a0=2, a1=0x800A3070)
    assert e.command_name == "Setfilter"


def test_cd_command_event_round_trips(tmp_path):
    path = str(tmp_path / "trace.jsonl")
    e = CdCommandEvent(t=1.0, call_site_addr=0x8008182C, command_byte=0x0D, a0=2, a1=0x800A3070, cpu_pc=0x8008182C, frame=5)
    with open(path, "w", encoding="utf-8") as f:
        write_event(e, f)
    assert load_trace(path) == [e]


# --- merge_traces ---------------------------------------------------------------


def test_merge_traces_sorts_by_timestamp_across_files(tmp_path):
    path_a = str(tmp_path / "a.jsonl")
    path_b = str(tmp_path / "b.jsonl")
    with open(path_a, "w", encoding="utf-8") as f:
        write_event(HeartbeatEvent(t=0.0, position_counter=1, lifecycle_state_raw=0, last_req_params=0), f)
        write_event(HeartbeatEvent(t=3.0, position_counter=2, lifecycle_state_raw=0, last_req_params=0), f)
    with open(path_b, "w", encoding="utf-8") as f:
        write_event(MarkEvent(t=1.5, label="mark"), f)

    merged = merge_traces(path_a, path_b)
    assert [round(e.t, 2) for e in merged] == [0.0, 1.5, 3.0]
    assert isinstance(merged[1], MarkEvent)
