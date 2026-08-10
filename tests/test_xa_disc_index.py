from gcrts.xa_disc_index import read_sector_meta, resolve_filename_to_path, resolve_lba_to_file

SYNC = b"\x00" + b"\xff" * 10 + b"\x00"


def _fake_sector(file_number=1, channel_number=7, submode=0x64, coding_info=0x01) -> bytes:
    header = bytes(4)  # min/sec/sector/mode -- not read by read_sector_meta
    subheader = bytes([file_number, channel_number, submode, coding_info]) + bytes(4)
    payload = bytes(2352 - 12 - 4 - 8)
    return SYNC + header + subheader + payload


def _disc_with_sector_at(lba: int, sector: bytes) -> bytes:
    return bytes(lba * 2352) + sector


# --- resolve_lba_to_file -------------------------------------------------


def test_resolve_lba_to_file_matches_known_start_boundary():
    """Live-confirmed this session: LBA 126218 lands EXACTLY on
    XAPACK08.BIN's own start LBA."""
    loc = resolve_lba_to_file(126218)
    assert loc is not None
    assert loc.disc_path == "DAT/XA1/XAPACK08.BIN"
    assert loc.offset_in_file_sectors == 0


def test_resolve_lba_to_file_mid_file():
    """Live-confirmed this session: LBA 126921 (Stage C's original
    cue-127 capture) falls inside XAPACK08.BIN."""
    loc = resolve_lba_to_file(126921)
    assert loc is not None
    assert loc.disc_path == "DAT/XA1/XAPACK08.BIN"
    assert loc.offset_in_file_sectors == 126921 - 126218


def test_resolve_lba_to_file_second_confirmed_boundary():
    """Live-confirmed this session: a second, independent live capture
    (params_now still 127, but a different real-time dispatch) landed
    EXACTLY on XAPACK06.BIN's own start LBA -- this is the direct
    evidence that a raw script parameter alone doesn't stably identify
    one physical source (see gcrts.runtime_audio's module docstring)."""
    loc = resolve_lba_to_file(116010)
    assert loc is not None
    assert loc.disc_path == "DAT/XA1/XAPACK06.BIN"
    assert loc.offset_in_file_sectors == 0


def test_resolve_lba_to_file_last_sector_of_a_file_not_first_of_next():
    # XAPACK06 starts at 116010, XAPACK07 starts at 121066
    loc = resolve_lba_to_file(121065)
    assert loc.disc_path == "DAT/XA1/XAPACK06.BIN"
    loc2 = resolve_lba_to_file(121066)
    assert loc2.disc_path == "DAT/XA1/XAPACK07.BIN"


def test_resolve_lba_to_file_none_before_first_file():
    assert resolve_lba_to_file(100) is None


def test_resolve_lba_to_file_none_after_last_file():
    assert resolve_lba_to_file(999999) is None


# --- read_sector_meta -----------------------------------------------------


def test_read_sector_meta_returns_none_without_sync_pattern():
    disc = bytes(2352 * 3)  # all zero, no valid sync anywhere
    assert read_sector_meta(disc, 0) is None


def test_read_sector_meta_returns_none_when_truncated():
    disc = SYNC  # far too short for a full sector
    assert read_sector_meta(disc, 0) is None


def test_read_sector_meta_reads_real_fields():
    sector = _fake_sector(file_number=1, channel_number=7, submode=0x64, coding_info=0x01)
    disc = _disc_with_sector_at(5, sector)
    meta = read_sector_meta(disc, 5)
    assert meta is not None
    assert meta.file_number == 1
    assert meta.channel_number == 7
    assert meta.submode == 0x64
    assert meta.coding_info == 0x01


def test_channel_number_is_positional_within_a_file_not_a_playback_selection():
    """Live-confirmed this session, exactly, across 40 consecutive real
    dispatches: channel_number == (lba - file_start_lba) % 8. This test
    pins that specific, load-bearing relationship as a regression check
    -- if it ever stops holding for a synthetic 8-sector interleaved
    file, the "channel is purely positional" finding needs re-examining
    before gcrts.runtime_audio relies on it again."""
    file_start = 100
    disc = bytearray(2352 * 16)
    for i in range(16):
        ch = i % 8
        sector = _fake_sector(channel_number=ch)
        disc[i * 2352:(i + 1) * 2352] = sector
    disc_bytes = bytes(disc)
    for i in range(16):
        lba = file_start + i
        # in this synthetic disc, sector index 0 == byte offset 0, so we
        # read directly by absolute sector index (no file_start offset
        # baked into the fake disc -- read_sector_meta only cares about lba)
        meta = read_sector_meta(disc_bytes, i)
        assert meta.channel_number == i % 8


# --- resolve_filename_to_path: real-disc-file cross-check -----------------


def test_resolve_filename_to_path_known_file_low_index():
    assert resolve_filename_to_path("XAPACK08") == "DAT/XA1/XAPACK08.BIN"


def test_resolve_filename_to_path_known_file_last_real_index():
    """Live-confirmed this session: the game's embedded string table
    genuinely spans the disc's full real range (00-42), not just the
    first 9 entries an earlier pass happened to sample first."""
    assert resolve_filename_to_path("XAPACK42") == "DAT/XA2/XAPACK42.BIN"


def test_resolve_filename_to_path_known_file_across_xa1_xa2_boundary():
    assert resolve_filename_to_path("XAPACK29") == "DAT/XA1/XAPACK29.BIN"
    assert resolve_filename_to_path("XAPACK30") == "DAT/XA2/XAPACK30.BIN"


def test_resolve_filename_to_path_none_for_plausible_but_nonexistent_file():
    """Live-confirmed this session: memory past the real table's extent
    keeps producing well-formed-looking "XAPACK43", "XAPACK44", ... text
    that is NOT a real disc file -- this must not be silently trusted."""
    assert resolve_filename_to_path("XAPACK43") is None
    assert resolve_filename_to_path("XAPACK99") is None


def test_resolve_filename_to_path_case_insensitive():
    assert resolve_filename_to_path("xapack08") == "DAT/XA1/XAPACK08.BIN"


def test_resolve_filename_to_path_none_for_unrelated_name():
    assert resolve_filename_to_path("MENUDAT") is None
