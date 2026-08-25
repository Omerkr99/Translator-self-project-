"""Tests for gcrts.movie_loader_scan -- built entirely against small
synthetic executable blobs, not the real multi-GB disc image (same
convention as tests/test_iso9660.py), so this suite runs anywhere."""
from __future__ import annotations

from gcrts.mips_disasm import decode_instruction
from gcrts.movie_loader_scan import (
    CallSiteClassification,
    HEADER_SIZE,
    MOVIE_TABLE_NAMES,
    find_call_sites,
    find_dispatcher,
    find_movie_name_table,
    trace_register_backward,
)

T_ADDR = 0x80035000


def _lui(rt: int, imm: int) -> int:
    return (0x0F << 26) | (rt << 16) | (imm & 0xFFFF)


def _addiu(rt: int, rs: int, imm: int) -> int:
    return (0x09 << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def _ori(rt: int, rs: int, imm: int) -> int:
    return (0x0D << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def _andi(rt: int, rs: int, imm: int) -> int:
    return (0x0C << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def _sll(rd: int, rt: int, sh: int) -> int:
    return (rt << 16) | (rd << 11) | (sh << 6) | 0x00


def _addu(rd: int, rs: int, rt: int) -> int:
    return (rs << 21) | (rt << 16) | (rd << 11) | 0x21


def _lw(rt: int, rs: int, imm: int) -> int:
    return (0x23 << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def _sw(rt: int, rs: int, imm: int) -> int:
    return (0x2B << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def _jal(pc: int, target: int) -> int:
    return (0x03 << 26) | (((target & 0x0FFFFFFC) >> 2))


def _jr(rs: int) -> int:
    return (rs << 21) | 0x08


NOP = 0
A0, A1, V0, V1, SP, RA = 4, 5, 2, 3, 29, 31


def _pack_words(words: list[int]) -> bytes:
    return b"".join(w.to_bytes(4, "little") for w in words)


def test_find_movie_name_table_locates_all_present_names():
    data = bytearray(HEADER_SIZE + 0x400)
    off = HEADER_SIZE + 0x10
    for name in MOVIE_TABLE_NAMES:
        s = b"\\" + name.encode() + b";1\x00\x00\x00\x00"
        data[off : off + len(s)] = s
        off += len(s)
    table = find_movie_name_table(bytes(data), T_ADDR)
    assert table is not None
    assert len(table.entries) == 10
    names_found = {e.name for e in table.entries}
    assert names_found == set(MOVIE_TABLE_NAMES)


def test_find_movie_name_table_returns_none_when_absent():
    data = bytes(HEADER_SIZE + 0x100)
    assert find_movie_name_table(data, T_ADDR) is None


def test_trace_register_backward_resolves_immediate_constant():
    # jal at idx 10; delay slot (idx 11) sets $a1 = 8 directly.
    instrs_words = [NOP] * 20
    instrs_words[9] = _addiu(SP, SP, -32)  # prologue
    instrs_words[10] = _jal(0, 0x80000000)
    instrs_words[11] = _ori(A1, 0, 8)
    instrs = [decode_instruction(T_ADDR + i * 4, w) for i, w in enumerate(instrs_words)]
    trace = trace_register_backward(instrs, 10, A1)
    assert trace.classification == CallSiteClassification.STATIC_CODE_MATCH
    assert trace.resolved_movie_id == 8


def test_trace_register_backward_follows_register_copy():
    # $s0 set to 3 earlier, then moved into $a1 in the delay slot via addu a1,s0,zero
    S0 = 16
    instrs_words = [NOP] * 20
    instrs_words[5] = _addiu(SP, SP, -32)
    instrs_words[6] = _ori(S0, 0, 3)
    instrs_words[10] = _jal(0, 0x80000000)
    instrs_words[11] = _addu(A1, S0, 0)  # move $a1, $s0
    instrs = [decode_instruction(T_ADDR + i * 4, w) for i, w in enumerate(instrs_words)]
    trace = trace_register_backward(instrs, 10, A1)
    assert trace.classification == CallSiteClassification.STATIC_CODE_MATCH
    assert trace.resolved_movie_id == 3


def test_trace_register_backward_detects_global_memory_load():
    V1 = 3
    instrs_words = [NOP] * 20
    instrs_words[4] = _addiu(SP, SP, -32)
    instrs_words[5] = _lui(V1, 0x8009)
    instrs_words[6] = _addiu(V1, V1, 0x100)
    instrs_words[7] = _lw(A1, V1, 0)
    instrs_words[10] = _jal(0, 0x80000000)
    instrs_words[11] = NOP  # no delay-slot write to a1
    instrs = [decode_instruction(T_ADDR + i * 4, w) for i, w in enumerate(instrs_words)]
    trace = trace_register_backward(instrs, 10, A1)
    assert trace.classification == CallSiteClassification.PARTIAL_STATIC
    assert "global memory address" in trace.note


def test_trace_register_backward_detects_parameter_passthrough():
    # a1 never (re)defined anywhere in this tiny function -> DYNAMIC_SELECTOR
    instrs_words = [NOP] * 20
    instrs_words[8] = _addiu(SP, SP, -32)
    instrs_words[10] = _jal(0, 0x80000000)
    instrs_words[11] = NOP
    instrs = [decode_instruction(T_ADDR + i * 4, w) for i, w in enumerate(instrs_words)]
    trace = trace_register_backward(instrs, 10, A1)
    assert trace.classification == CallSiteClassification.DYNAMIC_SELECTOR
    assert "incoming parameter" in trace.note


def test_find_dispatcher_and_call_sites_end_to_end():
    """A minimal but complete synthetic file: 10 movie-name strings, a
    dispatcher function that references the format string and a pointer
    table, and one caller passing a hardcoded movie_id -- end to end
    through find_movie_name_table -> find_dispatcher -> find_call_sites."""
    data = bytearray(HEADER_SIZE + 0x2000)

    # Layout (file offsets):
    name_area = HEADER_SIZE + 0x10
    fmt_string_off = HEADER_SIZE + 0x200
    pointer_table_off = HEADER_SIZE + 0x300
    dispatcher_code_off = HEADER_SIZE + 0x400
    caller_code_off = HEADER_SIZE + 0x600

    off = name_area
    name_ram_by_name = {}
    for name in MOVIE_TABLE_NAMES:
        s = b"\\" + name.encode() + b";1\x00\x00\x00\x00"
        data[off : off + len(s)] = s
        name_ram_by_name[name] = T_ADDR + (off - HEADER_SIZE)
        off += len(s)

    fmt_bytes = b"MovieLoad Exec : %s\x00"
    data[fmt_string_off : fmt_string_off + len(fmt_bytes)] = fmt_bytes
    fmt_ram = T_ADDR + (fmt_string_off - HEADER_SIZE)

    # Pointer table: 10 entries, index 3 points at MPRO.EXE's string (an
    # arbitrary index, chosen only to prove the resolver reads real
    # pointer values rather than assuming table order).
    table_base_ram = T_ADDR + (pointer_table_off - HEADER_SIZE)
    table_names_in_order = list(MOVIE_TABLE_NAMES)
    for i, name in enumerate(table_names_in_order):
        ptr = name_ram_by_name[name]
        data[pointer_table_off + i * 4 : pointer_table_off + i * 4 + 4] = ptr.to_bytes(4, "little")

    # Dispatcher function at dispatcher_code_off:
    #   addiu sp,sp,-32          (prologue)
    #   andi  v0, a1, 0xFF
    #   lui   v1, HI(table_base)
    #   addiu v1, v1, LO(table_base)
    #   sll   v0, v0, 2
    #   addu  v0, v0, v1
    #   lw    a1, 0(v0)
    #   lui   a0, HI(fmt_ram)
    #   addiu a0, a0, LO(fmt_ram)
    #   jr    ra
    words_at = {}
    V1 = 3

    def put(word_off_bytes, val):
        data[word_off_bytes : word_off_bytes + 4] = (val & 0xFFFFFFFF).to_bytes(4, "little")

    d = dispatcher_code_off
    put(d + 0x00, _addiu(SP, SP, -32))
    put(d + 0x04, _andi(V0, A1, 0xFF))
    hi = (table_base_ram >> 16) & 0xFFFF
    lo = table_base_ram & 0xFFFF
    lo_signed = lo - 0x10000 if lo & 0x8000 else lo
    hi_adj = hi + (1 if lo & 0x8000 else 0)
    put(d + 0x08, _lui(V1, hi_adj))
    put(d + 0x0C, _addiu(V1, V1, lo_signed))
    put(d + 0x10, _sll(V0, V0, 2))
    put(d + 0x14, _addu(V0, V0, V1))
    put(d + 0x18, _lw(A1, V0, 0))
    fmt_hi = (fmt_ram >> 16) & 0xFFFF
    fmt_lo = fmt_ram & 0xFFFF
    fmt_lo_signed = fmt_lo - 0x10000 if fmt_lo & 0x8000 else fmt_lo
    fmt_hi_adj = fmt_hi + (1 if fmt_lo & 0x8000 else 0)
    put(d + 0x1C, _lui(A0, fmt_hi_adj))
    put(d + 0x20, _addiu(A0, A0, fmt_lo_signed))
    put(d + 0x24, _jr(RA))

    dispatcher_entry_ram = T_ADDR + (d - HEADER_SIZE)

    # Caller: jal dispatcher_entry; delay slot sets a1 = 3 (index of MCAVE.EXE).
    c = caller_code_off
    caller_ram = T_ADDR + (c - HEADER_SIZE)
    jal_word = (0x03 << 26) | ((dispatcher_entry_ram & 0x0FFFFFFC) >> 2)
    put(c, jal_word)
    put(c + 4, _ori(A1, 0, 3))

    data = bytes(data)
    name_table = find_movie_name_table(data, T_ADDR)
    assert name_table is not None
    dispatcher = find_dispatcher(data, T_ADDR, name_table)
    assert dispatcher is not None
    assert dispatcher.entry_ram == dispatcher_entry_ram
    assert dispatcher.pointer_table_base_ram == table_base_ram

    resolved_names = [MOVIE_TABLE_NAMES[i] if i is not None else None for i in dispatcher.pointer_table_entries]
    assert resolved_names == table_names_in_order

    sites = find_call_sites(data, T_ADDR, dispatcher)
    assert len(sites) == 1
    assert sites[0].caller_ram == caller_ram
    assert sites[0].classification == CallSiteClassification.STATIC_CODE_MATCH
    assert sites[0].resolved_movie_id == 3
    assert sites[0].resolved_movie_name == "MCAVE.EXE"
