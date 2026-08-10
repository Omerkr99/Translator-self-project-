import struct

from gcrts.audio_event_extraction import (
    ExtractionConfidence,
    extract_runtime_audio_event,
    extraction_readiness,
    select_event_sectors,
)

SECTOR_SIZE = 2352
SYNC = b"\x00" + b"\xff" * 10 + b"\x00"
AUDIO_FLAG = 0x04
FORM2_FLAG = 0x20
DATA_FLAG = 0x08


def _sector(file_number: int, channel_number: int, submode: int, payload_byte: int = 0xAA) -> bytes:
    """Build one synthetic 2352-byte sector with a real sync pattern and
    subheader, matching the exact layout gcrts.xa_disc_index.read_sector_meta
    and gcrts.cdrom both already parse."""
    header = bytes(4)  # min/sec/sector + mode -- not inspected by this module
    coding_info = 0
    subheader = bytes([file_number, channel_number, submode, coding_info])
    body = bytes([payload_byte]) * (SECTOR_SIZE - len(SYNC) - len(header) - len(subheader))
    sector = SYNC + header + subheader + body
    assert len(sector) == SECTOR_SIZE
    return sector


def _disc(sectors_by_lba: dict) -> bytes:
    """Builds a disc image large enough to hold every given LBA, filling
    gaps with non-sync (invalid) sectors."""
    max_lba = max(sectors_by_lba) if sectors_by_lba else 0
    buf = bytearray(b"\x00" * SECTOR_SIZE * (max_lba + 1))
    for lba, sector in sectors_by_lba.items():
        buf[lba * SECTOR_SIZE : lba * SECTOR_SIZE + SECTOR_SIZE] = sector
    return bytes(buf)


# --- select_event_sectors ---------------------------------------------


def test_selects_only_matching_file_and_channel_audio_sectors():
    """8-way interleave: channels 0-7 all present in the range, only
    channel 1 of file 2 should be selected."""
    sectors = {}
    for lba in range(100, 108):
        channel = lba - 100
        sectors[lba] = _sector(file_number=2, channel_number=channel, submode=AUDIO_FLAG | FORM2_FLAG)
    disc = _disc(sectors)
    selected = select_event_sectors(disc, start_lba=100, end_lba=108, xa_file_number=2, xa_channel=1)
    assert selected == [101]


def test_excludes_sectors_from_a_different_file_number():
    sectors = {
        100: _sector(file_number=2, channel_number=1, submode=AUDIO_FLAG | FORM2_FLAG),
        101: _sector(file_number=3, channel_number=1, submode=AUDIO_FLAG | FORM2_FLAG),
    }
    disc = _disc(sectors)
    selected = select_event_sectors(disc, 100, 102, xa_file_number=2, xa_channel=1)
    assert selected == [100]


def test_excludes_non_audio_sectors_even_if_file_and_channel_match():
    sectors = {
        100: _sector(file_number=2, channel_number=1, submode=DATA_FLAG | FORM2_FLAG),  # data, not audio
        101: _sector(file_number=2, channel_number=1, submode=AUDIO_FLAG | FORM2_FLAG),
    }
    disc = _disc(sectors)
    selected = select_event_sectors(disc, 100, 102, xa_file_number=2, xa_channel=1)
    assert selected == [101]


def test_preserves_physical_lba_order():
    sectors = {
        lba: _sector(file_number=2, channel_number=1, submode=AUDIO_FLAG | FORM2_FLAG)
        for lba in (100, 108, 116)
    }
    disc = _disc(sectors)
    selected = select_event_sectors(disc, 100, 120, xa_file_number=2, xa_channel=1)
    assert selected == [100, 108, 116]


def test_skips_sectors_missing_the_real_sync_pattern():
    disc = bytearray(b"\x00" * SECTOR_SIZE * 3)
    good = _sector(file_number=2, channel_number=1, submode=AUDIO_FLAG | FORM2_FLAG)
    disc[1 * SECTOR_SIZE : 1 * SECTOR_SIZE + SECTOR_SIZE] = good
    selected = select_event_sectors(bytes(disc), 0, 3, xa_file_number=2, xa_channel=1)
    assert selected == [1]


# --- extract_runtime_audio_event ---------------------------------------


def test_extract_ready_when_matching_sectors_found():
    sectors = {
        100: _sector(2, 1, AUDIO_FLAG | FORM2_FLAG, payload_byte=0x11),
        101: _sector(2, 1, AUDIO_FLAG | FORM2_FLAG, payload_byte=0x22),
    }
    disc = _disc(sectors)
    result = extract_runtime_audio_event(disc, start_lba=100, end_lba=102, xa_file_number=2, xa_channel=1, event_id="e1")
    assert result.confidence == ExtractionConfidence.READY
    assert result.sector_count == 2
    assert result.physical_lbas == [100, 101]
    assert len(result.raw_xa_payload) == 2 * 2324
    assert result.raw_xa_payload[:1] == b"\x11"


def test_extract_end_unresolved_when_end_lba_is_none():
    disc = _disc({100: _sector(2, 1, AUDIO_FLAG | FORM2_FLAG)})
    result = extract_runtime_audio_event(disc, start_lba=100, end_lba=None, xa_file_number=2, xa_channel=1)
    assert result.confidence == ExtractionConfidence.END_UNRESOLVED
    assert result.sector_count == 0
    assert result.raw_xa_payload == b""


def test_extract_channel_confirmed_when_no_matching_sectors_in_range():
    """A real range with real sectors, but none match the given filter --
    honestly reports CHANNEL_CONFIRMED (attempted, nothing found), not
    READY with zero sectors silently passed off as success."""
    disc = _disc({100: _sector(2, 5, AUDIO_FLAG | FORM2_FLAG)})  # wrong channel
    result = extract_runtime_audio_event(disc, start_lba=100, end_lba=101, xa_file_number=2, xa_channel=1)
    assert result.confidence == ExtractionConfidence.CHANNEL_CONFIRMED
    assert result.sector_count == 0


def test_extract_never_defaults_file_or_channel():
    """Regression: this module must never silently assume the historical
    Setfilter(file=2, channel=1) observation applies -- caller must
    always supply explicit values."""
    disc = _disc({100: _sector(9, 3, AUDIO_FLAG | FORM2_FLAG)})
    result = extract_runtime_audio_event(disc, start_lba=100, end_lba=101, xa_file_number=9, xa_channel=3)
    assert result.xa_file_number == 9
    assert result.xa_channel == 3
    assert result.confidence == ExtractionConfidence.READY


def test_extract_preserves_provenance():
    disc = _disc({100: _sector(2, 1, AUDIO_FLAG | FORM2_FLAG)})
    prov = {"script_unit_id": "u42", "selector": 7}
    result = extract_runtime_audio_event(disc, 100, 101, 2, 1, provenance=prov)
    assert result.provenance == prov
    assert result.to_dict()["provenance"] == prov


# --- extraction_readiness (pure classification) -------------------------


def test_readiness_not_ready_without_start_lba():
    assert extraction_readiness(None, None, None, None) == ExtractionConfidence.NOT_READY


def test_readiness_start_confirmed_without_channel():
    assert extraction_readiness(100, None, None, None) == ExtractionConfidence.START_CONFIRMED


def test_readiness_channel_confirmed_without_end():
    assert extraction_readiness(100, None, 2, 1) == ExtractionConfidence.CHANNEL_CONFIRMED


def test_readiness_ready_with_everything_known():
    assert extraction_readiness(100, 200, 2, 1) == ExtractionConfidence.READY
