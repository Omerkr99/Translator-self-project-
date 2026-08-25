"""Tests for gcrts.disc_text_patch -- pure logic only. The real
build_patched_disc_copy() (file I/O against the actual multi-hundred-MB
disc image) is exercised manually, not by this synthetic suite --
matching this project's own convention for real-disc-scale operations.
"""
from __future__ import annotations

import struct

import pytest

from gcrts.disc_text_patch import find_script_text_offset, logical_offset_to_physical


def test_find_script_text_offset_locates_exact_match():
    codes = [2, 35072, 36098, 78, 52]
    needle = struct.pack("<5H", *codes)
    haystack = b"\x00" * 100 + needle + b"\x00" * 50
    assert find_script_text_offset(haystack, codes) == 100


def test_find_script_text_offset_returns_none_when_absent():
    codes = [1, 2, 3]
    haystack = b"\x00" * 200
    assert find_script_text_offset(haystack, codes) is None


def test_find_script_text_offset_finds_first_of_multiple_matches():
    codes = [10, 20]
    needle = struct.pack("<2H", *codes)
    haystack = b"\x00" * 10 + needle + b"\x00" * 10 + needle
    assert find_script_text_offset(haystack, codes) == 10


def test_logical_offset_to_physical_matches_real_disc_math():
    # Real values confirmed this session against the actual disc image:
    # K1LINK.CDB at LBA 186894, logical offset 3176838 -> physical
    # offset 443223054 (independently verified by reading both the
    # extracted logical bytes and the raw .bin bytes at this physical
    # offset and finding them identical).
    assert logical_offset_to_physical(file_lba=186894, logical_offset=3176838) == 443223054


def test_logical_offset_to_physical_first_byte_of_file():
    from gcrts.cdrom import HEADER_SIZE, SECTOR_SIZE

    assert logical_offset_to_physical(file_lba=100, logical_offset=0) == 100 * SECTOR_SIZE + HEADER_SIZE


def test_logical_offset_to_physical_crosses_a_sector_boundary():
    from gcrts.cdrom import HEADER_SIZE, SECTOR_SIZE

    # exactly at the start of the second logical block (2048)
    result = logical_offset_to_physical(file_lba=100, logical_offset=2048)
    assert result == 101 * SECTOR_SIZE + HEADER_SIZE
