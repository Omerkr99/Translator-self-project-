import struct

from gcrts.runtime_audio import (
    AudioConfidence,
    AudioLifecycleState,
    AudioPollSample,
    AudioProfile,
    RuntimeAudioEvent,
    capture_audio_event,
    compute_playback_offset_ms,
    validate_profile,
)

FP_ADDR = 0x800760B4
FP_BYTES = bytes.fromhex("e0ffbd27211080002118a0002140c0000a80013c176127a0")

STATE_ADDR = 0x800A6106
PARAMS_ADDR = 0x800A6114
POSITION_ADDR = 0x800A61AC


def _profile(**overrides) -> AudioProfile:
    kwargs = dict(
        profile_name="test_audio_profile",
        state_pair_addr=STATE_ADDR,
        last_req_params_addr=PARAMS_ADDR,
        position_addr=POSITION_ADDR,
        fingerprint_addr=FP_ADDR,
        fingerprint_bytes=FP_BYTES,
    )
    kwargs.update(overrides)
    return AudioProfile(**kwargs)


def _ram(state_second_byte: int, params: bytes, position: int, fingerprint_ok: bool = True) -> dict:
    ram = {
        STATE_ADDR: bytes([0x00, state_second_byte]),
        PARAMS_ADDR: params,
        POSITION_ADDR: struct.pack("<I", position),
    }
    if fingerprint_ok:
        ram[FP_ADDR] = FP_BYTES
    return ram


def _reader(ram: dict):
    return lambda addr, length: ram.get(addr)


# --- profile validation ------------------------------------------------


def test_validate_profile_true_when_fingerprint_matches():
    profile = _profile()
    assert validate_profile(profile, _reader({FP_ADDR: FP_BYTES})) is True


def test_validate_profile_false_when_fingerprint_differs():
    profile = _profile()
    assert validate_profile(profile, _reader({FP_ADDR: b"\x00" * len(FP_BYTES)})) is False


def test_validate_profile_false_when_unreadable():
    profile = _profile()
    assert validate_profile(profile, _reader({})) is False


# --- capture_audio_event: profile gate ----------------------------------


def test_capture_returns_none_when_profile_invalid():
    profile = _profile()
    ram = _ram(0x01, b"\x7f\x00\x7f\x00", 1000, fingerprint_ok=False)
    assert capture_audio_event(_reader(ram), profile) is None


def test_capture_returns_none_when_nothing_ever_dispatched():
    """Raw state 0x00 AND all-zero params -- genuinely never requested,
    distinct from a confirmed STOPPED-after-playing (which also has
    all-zero params but a nonzero prior state)."""
    profile = _profile()
    ram = _ram(0x00, b"\x00\x00\x00\x00", 0)
    assert capture_audio_event(_reader(ram), profile) is None


# --- lifecycle state mapping (live-confirmed values) --------------------


def test_capture_maps_raw_0x01_to_playing():
    profile = _profile()
    ram = _ram(0x01, b"\x7f\x00\x7f\x00", 118340)
    ev = capture_audio_event(_reader(ram), profile)
    assert ev is not None
    assert ev.state == AudioLifecycleState.PLAYING
    assert ev.script_parameter == 127
    assert ev.position_counter == 118340


def test_capture_maps_raw_0x02_with_cleared_params_to_stopped():
    profile = _profile()
    ram = _ram(0x02, b"\x00\x00\x00\x00", 134014)
    ev = capture_audio_event(_reader(ram), profile)
    assert ev is not None
    assert ev.state == AudioLifecycleState.STOPPED
    assert ev.position_counter == 134014


def test_capture_maps_raw_0x00_to_starting_when_params_present():
    profile = _profile()
    ram = _ram(0x00, b"\x7f\x00\x7f\x00", 100000)
    ev = capture_audio_event(_reader(ram), profile)
    assert ev is not None
    assert ev.state == AudioLifecycleState.STARTING


def test_capture_reports_unknown_when_stopped_state_disagrees_with_params():
    """raw_state==0x02 (STOPPED) but params still nonzero was never
    observed live -- this combination must not be silently trusted."""
    profile = _profile()
    ram = _ram(0x02, b"\x7f\x00\x7f\x00", 500)
    ev = capture_audio_event(_reader(ram), profile)
    assert ev is not None
    assert ev.state == AudioLifecycleState.UNKNOWN


def test_capture_reports_unknown_for_unrecognized_raw_state():
    profile = _profile()
    ram = _ram(0x09, b"\x7f\x00\x7f\x00", 500)
    ev = capture_audio_event(_reader(ram), profile)
    assert ev is not None
    assert ev.state == AudioLifecycleState.UNKNOWN


# --- source resolution: live LBA first, static table only as fallback --
# (Audio Cue Resolution Generalization milestone -- see runtime_audio's
# own module docstring: the same raw script parameter was live-observed
# resolving to two DIFFERENT physical files, which is why live LBA
# resolution against the real disc table now takes priority over
# KNOWN_CUE_SOURCES.)


def test_capture_resolves_source_live_from_position_when_in_a_known_xapack_range():
    """position=126921 is Stage C's own original, live-confirmed LBA,
    inside DAT/XA1/XAPACK08.BIN's real range -- resolved live, not from
    the static table, even though script_parameter (127) also happens
    to be in KNOWN_CUE_SOURCES."""
    profile = _profile()
    ram = _ram(0x01, b"\x7f\x00\x7f\x00", 126921)
    ev = capture_audio_event(_reader(ram), profile)
    assert ev.source_file == "DAT/XA1/XAPACK08.BIN"
    assert ev.start_lba == 126921
    assert ev.resolution_method == "live_lba"
    assert ev.confidence == AudioConfidence.LIVE_LBA_RESOLVED
    assert ev.source_type == "voice"
    # no disc_bytes given -> channel cannot be live-resolved
    assert ev.xa_channel is None


def test_capture_resolves_source_live_even_for_a_different_file_same_param():
    """position=116010 is a SECOND live-confirmed LBA for the SAME raw
    script parameter (127), landing in a DIFFERENT file
    (DAT/XA1/XAPACK06.BIN) -- direct proof live resolution tracks the
    actual observed position, not a fixed per-parameter table entry."""
    profile = _profile()
    ram = _ram(0x01, b"\x7f\x00\x7f\x00", 116010)
    ev = capture_audio_event(_reader(ram), profile)
    assert ev.source_file == "DAT/XA1/XAPACK06.BIN"
    assert ev.resolution_method == "live_lba"


def test_capture_resolves_channel_from_disc_bytes_when_provided():
    """A synthetic 8-sector interleaved disc, channel == index % 8 --
    matches the live-confirmed positional relationship exactly."""
    profile = _profile()
    ram = _ram(0x01, b"\x7f\x00\x7f\x00", 3)  # lba=3 -> inside first table entry's range once padded

    def fake_sector(channel):
        sync = b"\x00" + b"\xff" * 10 + b"\x00"
        return sync + bytes(4) + bytes([1, channel, 0x64, 0x01]) + bytes(4) + bytes(2352 - 24)

    disc = bytearray(2352 * 2100)
    for i in range(2040, 2100):
        disc[i * 2352:(i + 1) * 2352] = fake_sector(i % 8)
    ram2 = _ram(0x01, b"\x7f\x00\x7f\x00", 2050)
    ev = capture_audio_event(_reader(ram2), profile, disc_bytes=bytes(disc))
    assert ev.source_file == "DAT/XA1/XAPACK00.BIN"  # table starts at 2034
    assert ev.xa_channel == 2050 % 8
    assert ev.confidence == AudioConfidence.POSITIONAL_UNCONFIRMED


def test_capture_falls_back_to_static_table_when_position_outside_any_known_file():
    """position=1 is before every known XAPACK file's start (the first
    entry begins at 2034) -- live resolution fails, so this is the one
    case where the historical KNOWN_CUE_SOURCES fallback is exercised."""
    profile = _profile()
    ram = _ram(0x01, b"\x7f\x00\x7f\x00", 1)
    ev = capture_audio_event(_reader(ram), profile)
    assert ev.source_file == "DAT/XA1/XAPACK08.BIN"
    assert ev.xa_channel == 7
    assert ev.start_lba == 126921
    assert ev.audio_category == 2
    assert ev.source_type == "voice"
    assert ev.resolution_method == "static_table"
    assert ev.confidence == AudioConfidence.STATIC_LOOKUP


def test_capture_reports_unknown_source_for_unmapped_cue_outside_any_known_range():
    profile = _profile()
    ram = _ram(0x01, b"\x2a\x00\x2a\x00", 1)  # param=42, not in KNOWN_CUE_SOURCES; position outside any file
    ev = capture_audio_event(_reader(ram), profile)
    assert ev.script_parameter == 42
    assert ev.source_file is None
    assert ev.xa_channel is None
    assert ev.source_type == "unknown"
    assert ev.resolution_method == "unresolved"


# --- prior chaining (position_counter_start / script_parameter carry) ---


def test_capture_carries_position_counter_start_across_same_cue():
    profile = _profile()
    ev1 = capture_audio_event(_reader(_ram(0x01, b"\x7f\x00\x7f\x00", 100)), profile)
    ev2 = capture_audio_event(_reader(_ram(0x01, b"\x7f\x00\x7f\x00", 250)), profile, prior=ev1)
    assert ev2.position_counter == 250
    assert ev2.position_counter_start == 100  # unchanged from ev1, not reset to 250


def test_capture_resets_position_counter_start_on_new_cue():
    profile = _profile()
    ev1 = capture_audio_event(_reader(_ram(0x01, b"\x7f\x00\x7f\x00", 100)), profile)
    # new dispatch: different script parameter
    ev2 = capture_audio_event(_reader(_ram(0x01, b"\x2a\x00\x2a\x00", 300)), profile, prior=ev1)
    assert ev2.script_parameter == 42
    assert ev2.position_counter_start == 300  # fresh start, not carried from ev1's cue


def test_capture_carries_script_parameter_forward_once_cleared():
    """Once STOPPED clears params to zero, the event should still know
    which cue just finished, not silently forget it."""
    profile = _profile()
    ev1 = capture_audio_event(_reader(_ram(0x01, b"\x7f\x00\x7f\x00", 100)), profile)
    ev2 = capture_audio_event(_reader(_ram(0x02, b"\x00\x00\x00\x00", 200)), profile, prior=ev1)
    assert ev2.state == AudioLifecycleState.STOPPED
    assert ev2.script_parameter == 127


# --- to_dict / from_dict round trip -------------------------------------


def test_event_round_trips_through_dict():
    profile = _profile()
    ev = capture_audio_event(_reader(_ram(0x01, b"\x7f\x00\x7f\x00", 118340)), profile)
    restored = RuntimeAudioEvent.from_dict(ev.to_dict())
    assert restored == ev


# --- compute_playback_offset_ms -----------------------------------------


def _playing_event(pos: int) -> RuntimeAudioEvent:
    return RuntimeAudioEvent(
        event_id="e",
        source_type="voice",
        script_parameter=127,
        audio_category=2,
        source_file="DAT/XA1/XAPACK08.BIN",
        xa_channel=7,
        start_lba=126921,
        resolution_method="static_table",
        position_counter=pos,
        position_counter_start=pos,
        playback_offset_ms=None,
        state=AudioLifecycleState.PLAYING,
        confidence=AudioConfidence.STATIC_LOOKUP,
    )


def _stopped_event() -> RuntimeAudioEvent:
    ev = _playing_event(999)
    ev.state = AudioLifecycleState.STOPPED
    return ev


def test_compute_playback_offset_ms_sums_consecutive_playing_gaps():
    samples = [
        AudioPollSample(t=0.0, event=_playing_event(100)),
        AudioPollSample(t=1.0, event=_playing_event(200)),
        AudioPollSample(t=2.5, event=_playing_event(300)),
    ]
    assert compute_playback_offset_ms(samples) == 2500.0


def test_compute_playback_offset_ms_resets_across_a_stop_gap():
    samples = [
        AudioPollSample(t=0.0, event=_playing_event(100)),
        AudioPollSample(t=1.0, event=_playing_event(200)),
        AudioPollSample(t=2.0, event=_stopped_event()),
        AudioPollSample(t=3.0, event=_playing_event(50)),  # a new span
    ]
    # only the 0.0->1.0 PLAYING gap counts; the stop breaks continuity and
    # the last sample has no PLAYING predecessor immediately before it
    assert compute_playback_offset_ms(samples) == 1000.0


def test_compute_playback_offset_ms_none_when_never_playing():
    samples = [AudioPollSample(t=0.0, event=None), AudioPollSample(t=1.0, event=_stopped_event())]
    assert compute_playback_offset_ms(samples) is None
