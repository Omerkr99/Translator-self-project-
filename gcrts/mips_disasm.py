"""General-purpose MIPS-I instruction decoder for static analysis of this
game's own executables. Built for the movie-loader architecture
investigation (`gcrts.movie_loader_scan`), which needed to read real
function bodies -- prologues, branches, register data flow -- rather
than match single fixed byte patterns the way `gcrts.cdrom_fifo_scanner`
does for one narrow purpose.

Only what's actually needed to read this game's compiled C code is
covered: no coprocessor/FPU instructions (this is a PS1 CPU program, no
GTE/FPU use expected in this kind of control-flow code), no delay-slot
simulation (callers reason about delay slots explicitly where it
matters, e.g. `gcrts.mips_jal_decoder` for JAL's own return-address
arithmetic). `gcrts.mips_jal_decoder.decode_jal` remains the source of
truth for JAL/J target arithmetic -- this module's own J/JAL decoding
defers to it rather than re-deriving that arithmetic a third time in
this project.
"""
from __future__ import annotations

from dataclasses import dataclass

from gcrts.mips_jal_decoder import J_OPCODE, JAL_OPCODE, decode_jal

REGISTER_NAMES: tuple[str, ...] = (
    "zero", "at", "v0", "v1", "a0", "a1", "a2", "a3",
    "t0", "t1", "t2", "t3", "t4", "t5", "t6", "t7",
    "s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7",
    "t8", "t9", "k0", "k1", "gp", "sp", "fp", "ra",
)

# Register-name -> index, for callers that want to specify a register by
# name (e.g. trace_register_backward(..., reg=reg_index("a1"))).
_NAME_TO_INDEX = {name: i for i, name in enumerate(REGISTER_NAMES)}


def reg_index(name: str) -> int:
    return _NAME_TO_INDEX[name]


def reg_name(index: int) -> str:
    return REGISTER_NAMES[index]


def sign_extend16(imm: int) -> int:
    return imm - 0x10000 if imm & 0x8000 else imm


@dataclass(frozen=True)
class Instruction:
    """One decoded MIPS-I instruction. `mnemonic`/`text` are for human
    display; every field a caller might want to reason about
    programmatically (op, rs, rt, rd, imm, target) is also broken out
    directly rather than requiring re-parsing `text`."""

    pc: int
    word: int
    op: str  # a short symbolic name, e.g. "lui", "addiu", "jal", "beq", "nop", "other"
    rs: int
    rt: int
    rd: int
    shamt: int
    imm: int  # raw 16-bit field, unsigned
    simm: int  # sign-extended imm
    target: int | None  # absolute target address for j/jal/branches; None otherwise
    text: str  # human-readable disassembly

    @property
    def is_call(self) -> bool:
        return self.op == "jal"

    @property
    def is_branch(self) -> bool:
        return self.op in ("beq", "bne", "blez", "bgtz", "bltz", "bgez")


def _fmt_reg(i: int) -> str:
    return f"${reg_name(i)}"


def decode_instruction(pc: int, word: int) -> Instruction:
    """Decode one 32-bit MIPS-I instruction word located at `pc`. Unknown
    or unimplemented opcodes decode as op="other" with a `.word 0x...`
    text rather than raising -- this is a best-effort disassembler for
    reading real compiled code, not a strict validator; callers that need
    to know a specific instruction was actually recognized should check
    `op != "other"`."""
    opcode = (word >> 26) & 0x3F
    rs = (word >> 21) & 0x1F
    rt = (word >> 16) & 0x1F
    rd = (word >> 11) & 0x1F
    shamt = (word >> 6) & 0x1F
    funct = word & 0x3F
    imm = word & 0xFFFF
    simm = sign_extend16(imm)

    def mk(op, target=None, text=None):
        return Instruction(pc=pc, word=word, op=op, rs=rs, rt=rt, rd=rd, shamt=shamt, imm=imm, simm=simm,
                            target=target, text=text if text is not None else op)

    if word == 0:
        return mk("nop", text="nop")

    if opcode == 0x00:  # SPECIAL
        r = _fmt_reg
        if funct == 0x00:
            return mk("sll", text=f"sll {r(rd)}, {r(rt)}, {shamt}")
        if funct == 0x02:
            return mk("srl", text=f"srl {r(rd)}, {r(rt)}, {shamt}")
        if funct == 0x03:
            return mk("sra", text=f"sra {r(rd)}, {r(rt)}, {shamt}")
        if funct == 0x04:
            return mk("sllv", text=f"sllv {r(rd)}, {r(rt)}, {r(rs)}")
        if funct == 0x08:
            return mk("jr", text=f"jr {r(rs)}")
        if funct == 0x09:
            return mk("jalr", text=f"jalr {r(rd)}, {r(rs)}")
        if funct == 0x20:
            return mk("add", text=f"add {r(rd)}, {r(rs)}, {r(rt)}")
        if funct == 0x21:
            return mk("addu", text=f"addu {r(rd)}, {r(rs)}, {r(rt)}")
        if funct == 0x22:
            return mk("sub", text=f"sub {r(rd)}, {r(rs)}, {r(rt)}")
        if funct == 0x23:
            return mk("subu", text=f"subu {r(rd)}, {r(rs)}, {r(rt)}")
        if funct == 0x24:
            return mk("and", text=f"and {r(rd)}, {r(rs)}, {r(rt)}")
        if funct == 0x25:
            return mk("or", text=f"or {r(rd)}, {r(rs)}, {r(rt)}")
        if funct == 0x26:
            return mk("xor", text=f"xor {r(rd)}, {r(rs)}, {r(rt)}")
        if funct == 0x27:
            return mk("nor", text=f"nor {r(rd)}, {r(rs)}, {r(rt)}")
        if funct == 0x2A:
            return mk("slt", text=f"slt {r(rd)}, {r(rs)}, {r(rt)}")
        if funct == 0x2B:
            return mk("sltu", text=f"sltu {r(rd)}, {r(rs)}, {r(rt)}")
        if funct == 0x10:
            return mk("mfhi", text=f"mfhi {r(rd)}")
        if funct == 0x12:
            return mk("mflo", text=f"mflo {r(rd)}")
        if funct == 0x18:
            return mk("mult", text=f"mult {r(rs)}, {r(rt)}")
        if funct == 0x19:
            return mk("multu", text=f"multu {r(rs)}, {r(rt)}")
        if funct == 0x1A:
            return mk("div", text=f"div {r(rs)}, {r(rt)}")
        if funct == 0x1B:
            return mk("divu", text=f"divu {r(rs)}, {r(rt)}")
        return mk("other", text=f".special funct=0x{funct:02X}")

    r = _fmt_reg
    if opcode == 0x0F:
        return mk("lui", text=f"lui {r(rt)}, 0x{imm:04X}")
    if opcode == 0x0D:
        return mk("ori", text=f"ori {r(rt)}, {r(rs)}, 0x{imm:04X}")
    if opcode == 0x0C:
        return mk("andi", text=f"andi {r(rt)}, {r(rs)}, 0x{imm:04X}")
    if opcode == 0x0E:
        return mk("xori", text=f"xori {r(rt)}, {r(rs)}, 0x{imm:04X}")
    if opcode == 0x08:
        return mk("addi", text=f"addi {r(rt)}, {r(rs)}, {simm}")
    if opcode == 0x09:
        return mk("addiu", text=f"addiu {r(rt)}, {r(rs)}, {simm}")
    if opcode == 0x0A:
        return mk("slti", text=f"slti {r(rt)}, {r(rs)}, {simm}")
    if opcode == 0x0B:
        return mk("sltiu", text=f"sltiu {r(rt)}, {r(rs)}, {simm}")
    if opcode == 0x23:
        return mk("lw", text=f"lw {r(rt)}, {simm}({r(rs)})")
    if opcode == 0x20:
        return mk("lb", text=f"lb {r(rt)}, {simm}({r(rs)})")
    if opcode == 0x24:
        return mk("lbu", text=f"lbu {r(rt)}, {simm}({r(rs)})")
    if opcode == 0x21:
        return mk("lh", text=f"lh {r(rt)}, {simm}({r(rs)})")
    if opcode == 0x25:
        return mk("lhu", text=f"lhu {r(rt)}, {simm}({r(rs)})")
    if opcode == 0x2B:
        return mk("sw", text=f"sw {r(rt)}, {simm}({r(rs)})")
    if opcode == 0x28:
        return mk("sb", text=f"sb {r(rt)}, {simm}({r(rs)})")
    if opcode == 0x29:
        return mk("sh", text=f"sh {r(rt)}, {simm}({r(rs)})")
    if opcode in (JAL_OPCODE, J_OPCODE):
        decoded = decode_jal(pc, word, allow_j=True)
        name = "jal" if opcode == JAL_OPCODE else "j"
        return mk(name, target=decoded.target, text=f"{name} 0x{decoded.target:08X}")
    if opcode == 0x04:
        target = pc + 4 + simm * 4
        return mk("beq", target=target, text=f"beq {r(rs)}, {r(rt)}, 0x{target:08X}")
    if opcode == 0x05:
        target = pc + 4 + simm * 4
        return mk("bne", target=target, text=f"bne {r(rs)}, {r(rt)}, 0x{target:08X}")
    if opcode == 0x06:
        target = pc + 4 + simm * 4
        return mk("blez", target=target, text=f"blez {r(rs)}, 0x{target:08X}")
    if opcode == 0x07:
        target = pc + 4 + simm * 4
        return mk("bgtz", target=target, text=f"bgtz {r(rs)}, 0x{target:08X}")
    if opcode == 0x01:
        target = pc + 4 + simm * 4
        if rt == 1:
            return mk("bgez", target=target, text=f"bgez {r(rs)}, 0x{target:08X}")
        if rt == 0:
            return mk("bltz", target=target, text=f"bltz {r(rs)}, 0x{target:08X}")
        return mk("other", text=f".regimm rt=0x{rt:02X}")
    return mk("other", text=f".word 0x{word:08X}")


def disassemble_range(data: bytes, file_start: int, file_end: int, t_addr: int, header_size: int = 0x800) -> list[Instruction]:
    """Decode every 4-byte-aligned word in `data[file_start:file_end]`,
    treating `file_start`/`file_end` as offsets into the raw ISO9660 file
    (including its 0x800-byte PS-EXE header) and mapping them to RAM
    addresses via `ram = t_addr + (file_offset - header_size)` -- the
    same convention this project's earlier ad hoc investigation scripts
    used, now centralized here."""
    out = []
    for off in range(file_start, file_end, 4):
        word = int.from_bytes(data[off : off + 4], "little")
        ram = t_addr + (off - header_size)
        out.append(decode_instruction(ram, word))
    return out
