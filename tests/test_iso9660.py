import struct

from gcrts.cdrom import SECTOR_SIZE, SYNC_PATTERN, HEADER_SIZE
from gcrts.iso9660 import read_directory, read_file, read_root_directory

_LOGICAL_BLOCK_SIZE = 2048


def make_sector(payload: bytes) -> bytes:
    header = b"\x00\x02\x00\x02"
    subheader = bytes([0x00, 0x00, 0x00, 0x00]) * 2
    padded = payload.ljust(_LOGICAL_BLOCK_SIZE, b"\x00")
    trailer_size = SECTOR_SIZE - HEADER_SIZE - _LOGICAL_BLOCK_SIZE
    sector = SYNC_PATTERN + header + subheader + padded + bytes(trailer_size)
    assert len(sector) == SECTOR_SIZE
    return sector


def make_dir_record(name: bytes, lba: int, size: int, is_dir: bool) -> bytes:
    rec = bytearray(33 + len(name))
    struct.pack_into("<I", rec, 2, lba)
    struct.pack_into("<I", rec, 10, size)
    rec[25] = 0x2 if is_dir else 0x0
    rec[32] = len(name)
    rec[33 : 33 + len(name)] = name
    if len(rec) % 2:
        rec.append(0)
    rec[0] = len(rec)
    return bytes(rec)


def make_pvd(root_lba: int, root_size: int) -> bytes:
    pvd = bytearray(_LOGICAL_BLOCK_SIZE)
    pvd[0] = 1
    pvd[1:6] = b"CD001"
    pvd[6] = 1
    root_record = make_dir_record(b"\x00", root_lba, root_size, is_dir=True)
    pvd[156 : 156 + len(root_record)] = root_record
    return bytes(pvd)


def build_disc() -> bytes:
    # Layout: LBA16=PVD, 17=root dir, 18=file TEST.TXT, 19=subdir, 20=SUB.TXT
    file_content = b"HELLO FROM TEST FILE"
    sub_content = b"HELLO FROM SUBDIR FILE"

    root_dir = (
        make_dir_record(b"\x00", 17, _LOGICAL_BLOCK_SIZE, is_dir=True)
        + make_dir_record(b"\x01", 17, _LOGICAL_BLOCK_SIZE, is_dir=True)
        + make_dir_record(b"TEST.TXT;1", 18, len(file_content), is_dir=False)
        + make_dir_record(b"SUBDIR", 19, _LOGICAL_BLOCK_SIZE, is_dir=True)
    )
    sub_dir = (
        make_dir_record(b"\x00", 19, _LOGICAL_BLOCK_SIZE, is_dir=True)
        + make_dir_record(b"\x01", 17, _LOGICAL_BLOCK_SIZE, is_dir=True)
        + make_dir_record(b"SUB.TXT;1", 20, len(sub_content), is_dir=False)
    )

    sectors = [bytes(_LOGICAL_BLOCK_SIZE)] * 16  # LBA 0-15: unused padding
    sectors.append(make_pvd(17, _LOGICAL_BLOCK_SIZE)[:_LOGICAL_BLOCK_SIZE])  # 16
    sectors.append(root_dir)  # 17
    sectors.append(file_content)  # 18
    sectors.append(sub_dir)  # 19
    sectors.append(sub_content)  # 20

    return b"".join(make_sector(s) for s in sectors)


def test_reads_root_directory_entries():
    disc = build_disc()
    entries = read_root_directory(disc)
    names = {e.name for e in entries}
    assert "TEST.TXT;1" in names
    assert "SUBDIR" in names


def test_reads_file_contents():
    disc = build_disc()
    entries = read_root_directory(disc)
    file_entry = next(e for e in entries if e.name == "TEST.TXT;1")
    assert read_file(disc, file_entry) == b"HELLO FROM TEST FILE"


def test_reads_subdirectory_and_its_file():
    disc = build_disc()
    entries = read_root_directory(disc)
    subdir_entry = next(e for e in entries if e.name == "SUBDIR")
    sub_entries = read_directory(disc, subdir_entry)
    sub_file = next(e for e in sub_entries if e.name == "SUB.TXT;1")
    assert read_file(disc, sub_file) == b"HELLO FROM SUBDIR FILE"


def test_rejects_missing_pvd():
    junk = bytes(SECTOR_SIZE * 20)
    try:
        read_root_directory(junk)
        assert False, "expected ValueError"
    except ValueError:
        pass
