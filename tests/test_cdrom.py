from gcrts.cdrom import SECTOR_SIZE, extract_sector_payloads

_SYNC = b"\x00" + b"\xff" * 10 + b"\x00"


def make_sector(payload: bytes, form2: bool = False) -> bytes:
    header = b"\x00\x02\x00\x02"  # min:sec:sector (BCD-ish, unchecked) + mode 2
    submode = 0x20 if form2 else 0x00
    subheader = bytes([0x00, 0x00, submode, 0x00]) * 2  # duplicated per spec
    data_size = 2324 if form2 else 2048
    padded_payload = payload.ljust(data_size, b"\x00")
    trailer_size = SECTOR_SIZE - 12 - len(header) - len(subheader) - data_size
    trailer = bytes(trailer_size)
    sector = _SYNC + header + subheader + padded_payload + trailer
    assert len(sector) == SECTOR_SIZE
    return sector


def test_extracts_form1_payload():
    sector = make_sector(b"HELLO FORM1")
    result = extract_sector_payloads(sector)
    assert result[:11] == b"HELLO FORM1"
    assert len(result) == 2048


def test_extracts_form2_payload():
    sector = make_sector(b"HELLO FORM2", form2=True)
    result = extract_sector_payloads(sector)
    assert result[:11] == b"HELLO FORM2"
    assert len(result) == 2324


def test_concatenates_multiple_sectors_in_order():
    data = make_sector(b"FIRST") + make_sector(b"SECOND")
    result = extract_sector_payloads(data)
    assert result[:5] == b"FIRST"
    assert result[2048:2054] == b"SECOND"
    assert len(result) == 2048 * 2


def test_skips_sectors_without_valid_sync():
    junk = bytes(SECTOR_SIZE)  # all zeros -- no sync pattern
    data = junk + make_sector(b"REAL DATA")
    result = extract_sector_payloads(data)
    assert result[:9] == b"REAL DATA"
    assert len(result) == 2048  # the junk sector contributed nothing


def test_empty_input():
    assert extract_sector_payloads(b"") == b""
