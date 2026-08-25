"""Tests for gcrts.mips_disasm -- hand-verified instruction encodings."""
from __future__ import annotations

from gcrts.mips_disasm import decode_instruction, disassemble_range, reg_index, reg_name


def test_nop_is_zero_word():
    instr = decode_instruction(0x80010000, 0x00000000)
    assert instr.op == "nop"


def test_lui_decodes_immediate_and_target_register():
    # lui $a0, 0x8004
    word = (0x0F << 26) | (4 << 16) | 0x8004
    instr = decode_instruction(0x80010000, word)
    assert instr.op == "lui"
    assert instr.rt == 4
    assert instr.imm == 0x8004


def test_addiu_sign_extends_negative_immediate():
    # addiu $sp, $sp, -32
    word = (0x09 << 26) | (29 << 21) | (29 << 16) | (0xFFE0)
    instr = decode_instruction(0x80010000, word)
    assert instr.op == "addiu"
    assert instr.rs == 29 and instr.rt == 29
    assert instr.simm == -32


def test_lw_decodes_base_and_offset():
    # lw $a1, 0($s0)  where $s0=16
    word = (0x23 << 26) | (16 << 21) | (5 << 16) | 0
    instr = decode_instruction(0x80010000, word)
    assert instr.op == "lw"
    assert instr.rs == 16 and instr.rt == 5 and instr.simm == 0


def test_jal_target_matches_mips_jal_decoder():
    from gcrts.mips_jal_decoder import decode_jal

    pc = 0x80029E18
    word = (0x03 << 26) | 0x0006B980  # arbitrary valid-looking JAL word
    expected = decode_jal(pc, word)
    instr = decode_instruction(pc, word)
    assert instr.op == "jal"
    assert instr.target == expected.target


def test_beq_target_uses_pc_plus_4_plus_offset_times_4():
    # beq $zero, $zero, +2 (branch 2 instructions ahead of the delay slot)
    word = (0x04 << 26) | (0 << 21) | (0 << 16) | 2
    pc = 0x80010000
    instr = decode_instruction(pc, word)
    assert instr.op == "beq"
    assert instr.target == pc + 4 + 2 * 4


def test_jr_ra_recognized():
    # jr $ra
    word = (0x00 << 26) | (31 << 21) | 0x08
    instr = decode_instruction(0x80010000, word)
    assert instr.op == "jr"
    assert instr.rs == 31


def test_unknown_opcode_falls_back_to_other_without_raising():
    word = 0xFFFFFFFF
    instr = decode_instruction(0x80010000, word)
    assert instr.op == "other"


def test_reg_index_and_reg_name_are_inverses():
    for i, name in enumerate(["zero", "at", "v0", "a0", "a1", "sp", "ra"]):
        idx = reg_index(name)
        assert reg_name(idx) == name


def test_disassemble_range_maps_file_offset_to_ram_address():
    # two words: nop, then lui $a0,0x8004 -- at file offset 0x800 (header
    # boundary) so ram should equal t_addr exactly for the first word.
    data = bytearray(0x810)
    lui_word = (0x0F << 26) | (4 << 16) | 0x8004
    data[0x800:0x804] = (0).to_bytes(4, "little")
    data[0x804:0x808] = lui_word.to_bytes(4, "little")
    instrs = disassemble_range(bytes(data), 0x800, 0x808, t_addr=0x80045000)
    assert len(instrs) == 2
    assert instrs[0].pc == 0x80045000
    assert instrs[1].pc == 0x80045004
    assert instrs[1].op == "lui" and instrs[1].imm == 0x8004
