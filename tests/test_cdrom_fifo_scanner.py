"""Tests for gcrts.cdrom_fifo_scanner -- the static MIPS data-flow
scanner built to answer whether CAP0.EXE reads the CD-ROM Data FIFO
(0x1F801802) after a live GDB watchpoint turned out to have latched
onto the neighboring Request/IRQ register (0x1F801803) instead."""
from __future__ import annotations

from gcrts.cdrom_fifo_scanner import (
    AccessType,
    DATA_FIFO_ADDR,
    RAM_BASE,
    scan_for_cdrom_register_accesses,
)

BASE_VADDR = 0x80045000


def _lui(rt: int, imm: int) -> int:
    return (0x0F << 26) | (rt << 16) | (imm & 0xFFFF)


def _lw(rs: int, rt: int, imm: int) -> int:
    return (0x23 << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def _lbu(rs: int, rt: int, imm: int) -> int:
    return (0x24 << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def _sb(rs: int, rt: int, imm: int) -> int:
    return (0x28 << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def _addu(rd: int, rs: int, rt: int) -> int:
    return (0x00 << 26) | (rs << 21) | (rt << 16) | (rd << 11) | 0x21


def _addiu(rt: int, rs: int, imm: int) -> int:
    return (0x09 << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def _nop() -> int:
    return 0


def _words_to_ram(words: list[int], base_vaddr: int = BASE_VADDR) -> bytes:
    data = bytearray(0x200000)
    off = base_vaddr - RAM_BASE
    for w in words:
        data[off:off + 4] = w.to_bytes(4, "little")
        off += 4
    return bytes(data)


def test_direct_literal_pointer_resolution_finds_read():
    # lui $2,0x800A ; lw $2,0x30C4($2) ; lbu $3,0($2)
    words = [_lui(2, 0x800A), _lw(2, 2, 0x30C4), _lbu(2, 3, 0)]
    data = _words_to_ram(words)
    result = scan_for_cdrom_register_accesses(data, BASE_VADDR, BASE_VADDR + len(words) * 4)
    reads = result.read_sites
    assert len(reads) == 1
    assert reads[0].effective_addr == DATA_FIFO_ADDR
    assert reads[0].access == AccessType.READ


def test_write_classified_as_write_not_read():
    words = [_lui(2, 0x800A), _lw(2, 2, 0x30C4), _sb(2, 3, 0)]
    data = _words_to_ram(words)
    result = scan_for_cdrom_register_accesses(data, BASE_VADDR, BASE_VADDR + len(words) * 4)
    assert len(result.write_sites) == 1
    assert len(result.read_sites) == 0
    assert result.write_sites[0].effective_addr == DATA_FIFO_ADDR


def test_neighboring_register_0x30c8_never_reported_as_data_fifo():
    # lui $2,0x800A ; lw $2,0x30C8($2) [Request/IRQ, NOT the FIFO] ; lbu $3,0($2)
    words = [_lui(2, 0x800A), _lw(2, 2, 0x30C8), _lbu(2, 3, 0)]
    data = _words_to_ram(words)
    result = scan_for_cdrom_register_accesses(data, BASE_VADDR, BASE_VADDR + len(words) * 4)
    assert all(s.effective_addr != DATA_FIFO_ADDR for s in result.sites)
    # it IS a real access to a different, adjacent CD register -- just not the FIFO
    assert any(s.effective_addr == 0x1F801803 for s in result.sites)


def test_register_copy_propagation():
    # lui $2,0x800A ; lw $2,0x30C4($2) ; addu $4,$2,$0 (move) ; lbu $5,0($4)
    words = [_lui(2, 0x800A), _lw(2, 2, 0x30C4), _addu(4, 2, 0), _lbu(4, 5, 0)]
    data = _words_to_ram(words)
    result = scan_for_cdrom_register_accesses(data, BASE_VADDR, BASE_VADDR + len(words) * 4)
    assert len(result.read_sites) == 1
    assert result.read_sites[0].effective_addr == DATA_FIFO_ADDR
    assert "copied" in result.read_sites[0].note


def test_base_plus_offset_pointer_arithmetic():
    # lui $2,0x800A ; lw $2,0x30BC($2) [Index/Status base] ; addiu $3,$2,2 (base+2 -> Data FIFO) ; lbu $4,0($3)
    words = [_lui(2, 0x800A), _lw(2, 2, 0x30BC), _addiu(3, 2, 2), _lbu(3, 4, 0)]
    data = _words_to_ram(words)
    result = scan_for_cdrom_register_accesses(data, BASE_VADDR, BASE_VADDR + len(words) * 4)
    assert len(result.read_sites) == 1
    assert result.read_sites[0].effective_addr == DATA_FIFO_ADDR


def test_tag_killed_on_unrelated_redefinition():
    # lui $2,0x800A ; lw $2,0x30C4($2) ; lui $2,0x1234 (kills the tag) ; lbu $3,0($2) -> must NOT be reported
    words = [_lui(2, 0x800A), _lw(2, 2, 0x30C4), _lui(2, 0x1234), _lbu(2, 3, 0)]
    data = _words_to_ram(words)
    result = scan_for_cdrom_register_accesses(data, BASE_VADDR, BASE_VADDR + len(words) * 4)
    assert len(result.sites) == 0


def test_no_false_positive_on_unrelated_code():
    words = [_lui(2, 0x1234), _addiu(2, 2, 0x10), _lbu(2, 3, 4), _nop(), _nop()]
    data = _words_to_ram(words)
    result = scan_for_cdrom_register_accesses(data, BASE_VADDR, BASE_VADDR + len(words) * 4)
    assert len(result.sites) == 0


def test_instructions_scanned_covers_full_requested_range():
    words = [_nop()] * 50
    data = _words_to_ram(words)
    result = scan_for_cdrom_register_accesses(data, BASE_VADDR, BASE_VADDR + len(words) * 4)
    assert result.instructions_scanned == 50


def test_passed_to_function_call_flagged_address_only():
    # lui $2,0x800A ; lw $2,0x30C4($2) ; addu $4,$2,$0 (into a0) ; jal target
    jal_target = 0x80050000
    jal_word = (0x03 << 26) | ((jal_target & 0x0FFFFFFF) >> 2)
    words = [_lui(2, 0x800A), _lw(2, 2, 0x30C4), _addu(4, 2, 0), jal_word]
    data = _words_to_ram(words)
    result = scan_for_cdrom_register_accesses(data, BASE_VADDR, BASE_VADDR + len(words) * 4)
    addr_only = result.address_only_sites
    assert len(addr_only) == 1
    assert addr_only[0].effective_addr == DATA_FIFO_ADDR
