"""Static MIPS data-flow scanner for CD-ROM register accesses within a
given executable range (built for CAP0.EXE, 0x80045000-0x800A4000).

Answers one specific question: does any code path read from the CD-ROM
Data FIFO hardware register (0x1F801802) into guest-visible CPU state?
Built after a live GDB read-watchpoint on that address turned out to
have latched onto the neighboring Request/IRQ register (0x1F801803)
instead, due to coarse watchpoint granularity -- this module exists to
answer the question statically and precisely before any further live
capture is attempted.

Approach: a single linear pass over the instruction stream (address
order, not execution order -- this is a real limitation, documented
below) that tracks, per GPR, whether it currently holds one of the four
known CD-ROM hardware register addresses. A register's tag is killed
the moment it is redefined by anything this scanner does not recognize
as tag-preserving (a plain register copy, or small-immediate pointer
arithmetic) -- this is the correctness mechanism, not a hand-picked
instruction window.

Known limitation: because this is a linear address-order scan, not a
control-flow-graph-aware one, a tag established on one path and killed
on another (e.g. across a branch) can be over- or under-approximated.
This is flagged explicitly in the final report rather than silently
assumed away.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

RAM_BASE = 0x80000000

OPCODE_SPECIAL = 0x00
OPCODE_LUI = 0x0F
OPCODE_ORI = 0x0D
OPCODE_ADDIU = 0x09
OPCODE_ANDI = 0x0C
OPCODE_LB = 0x20
OPCODE_LH = 0x21
OPCODE_LW = 0x23
OPCODE_LBU = 0x24
OPCODE_LHU = 0x25
OPCODE_SB = 0x28
OPCODE_SH = 0x29
OPCODE_SW = 0x2B
OPCODE_JAL = 0x03

LOAD_OPCODES = {OPCODE_LB, OPCODE_LH, OPCODE_LW, OPCODE_LBU, OPCODE_LHU}
STORE_OPCODES = {OPCODE_SB, OPCODE_SH, OPCODE_SW}

FUNCT_ADDU = 0x21
FUNCT_OR = 0x25
FUNCT_ADD = 0x20

# RAM variables this project already verified (live) hold these exact
# real hardware CD-ROM register addresses -- see docs/audio/XA_STREAM_RESOLUTION.md.
CD_POINTER_VARS: dict[int, int] = {
    0x30BC: 0x1F801800,  # Index/Status
    0x30C0: 0x1F801801,  # Command / Response FIFO
    0x30C4: 0x1F801802,  # Parameter FIFO / Data  <-- the one in question
    0x30C8: 0x1F801803,  # Request / IRQ enable-ack
}
CD_POINTER_HI = 0x800A

DATA_FIFO_ADDR = 0x1F801802

REGISTER_NAMES = {
    0: "zero", 1: "at", 2: "v0", 3: "v1", 4: "a0", 5: "a1", 6: "a2", 7: "a3",
}


class AccessType(str, Enum):
    READ = "READ"
    WRITE = "WRITE"
    ADDRESS_ONLY = "ADDRESS_ONLY"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class Instruction:
    addr: int
    word: int

    @property
    def opcode(self) -> int:
        return (self.word >> 26) & 0x3F

    @property
    def rs(self) -> int:
        return (self.word >> 21) & 0x1F

    @property
    def rt(self) -> int:
        return (self.word >> 16) & 0x1F

    @property
    def rd(self) -> int:
        return (self.word >> 11) & 0x1F

    @property
    def imm(self) -> int:
        return self.word & 0xFFFF

    @property
    def simm(self) -> int:
        v = self.imm
        return v - 0x10000 if v >= 0x8000 else v

    @property
    def funct(self) -> int:
        return self.word & 0x3F


@dataclass
class RegTag:
    address: int
    origin_pc: int
    via: str  # human-readable derivation chain


@dataclass
class FifoSite:
    pc: int
    access: AccessType
    effective_addr: int
    instruction_text: str
    pointer_origin_pc: int
    reg: int
    confidence: str
    note: str = ""

    @property
    def label(self) -> str:
        return f"CAP0.EXE:0x{self.pc:08X}"


def disassemble_range(data: bytes, start_vaddr: int, end_vaddr: int) -> list[Instruction]:
    """Reads every 4-byte-aligned word in [start_vaddr, end_vaddr) from a
    RAM image where offset 0 corresponds to guest address RAM_BASE."""
    instrs = []
    for vaddr in range(start_vaddr, end_vaddr, 4):
        off = vaddr - RAM_BASE
        if off < 0 or off + 4 > len(data):
            continue
        word = int.from_bytes(data[off:off + 4], "little")
        instrs.append(Instruction(vaddr, word))
    return instrs


def _reg_name(n: int) -> str:
    return REGISTER_NAMES.get(n, f"r{n}")


def _instr_text(instr: Instruction) -> str:
    op = instr.opcode
    if op == OPCODE_LUI:
        return f"lui ${_reg_name(instr.rt)}, 0x{instr.imm:04X}"
    if op == OPCODE_ORI:
        return f"ori ${_reg_name(instr.rt)}, ${_reg_name(instr.rs)}, 0x{instr.imm:04X}"
    if op == OPCODE_ADDIU:
        return f"addiu ${_reg_name(instr.rt)}, ${_reg_name(instr.rs)}, {instr.simm}"
    if op in LOAD_OPCODES:
        names = {OPCODE_LB: "lb", OPCODE_LH: "lh", OPCODE_LW: "lw", OPCODE_LBU: "lbu", OPCODE_LHU: "lhu"}
        return f"{names[op]} ${_reg_name(instr.rt)}, {instr.simm}(${_reg_name(instr.rs)})"
    if op in STORE_OPCODES:
        names = {OPCODE_SB: "sb", OPCODE_SH: "sh", OPCODE_SW: "sw"}
        return f"{names[op]} ${_reg_name(instr.rt)}, {instr.simm}(${_reg_name(instr.rs)})"
    if op == OPCODE_SPECIAL and instr.funct in (FUNCT_ADDU, FUNCT_OR):
        return f"{'addu' if instr.funct==FUNCT_ADDU else 'or'} ${_reg_name(instr.rd)}, ${_reg_name(instr.rs)}, ${_reg_name(instr.rt)}"
    if op == OPCODE_JAL:
        target = (instr.addr & 0xF0000000) | ((instr.word & 0x03FFFFFF) << 2)
        return f"jal 0x{target:08X}"
    return f".word 0x{instr.word:08X}"


@dataclass
class ScanResult:
    instructions_scanned: int
    functions_estimated: int
    sites: list[FifoSite] = field(default_factory=list)

    @property
    def read_sites(self) -> list[FifoSite]:
        return [s for s in self.sites if s.access == AccessType.READ]

    @property
    def write_sites(self) -> list[FifoSite]:
        return [s for s in self.sites if s.access == AccessType.WRITE]

    @property
    def address_only_sites(self) -> list[FifoSite]:
        return [s for s in self.sites if s.access == AccessType.ADDRESS_ONLY]

    @property
    def unknown_sites(self) -> list[FifoSite]:
        return [s for s in self.sites if s.access == AccessType.UNKNOWN]


def scan_for_cdrom_register_accesses(
    data: bytes, start_vaddr: int, end_vaddr: int, target_addr: int = DATA_FIFO_ADDR
) -> ScanResult:
    """Single linear pass. Tracks, per GPR (1-31, $zero excluded), a
    RegTag if that register currently holds a known CD-ROM hardware
    register address. A tag is killed the instant its register is
    redefined by anything not recognised below as tag-preserving."""
    instrs = disassemble_range(data, start_vaddr, end_vaddr)
    tags: dict[int, RegTag] = {}
    sites: list[FifoSite] = []
    jal_count = 0

    for i, instr in enumerate(instrs):
        op = instr.opcode

        # --- Pattern: LW $r2, <off>($r) where a preceding LUI $r,0x800A
        # established $r, and off is one of the 4 known pointer vars.
        # Detected AT the LW instruction (not the earlier LUI) so that
        # this same iteration's kill-logic (below) sees the tag it just
        # set and correctly preserves it.
        if op == OPCODE_LW and instr.imm in CD_POINTER_VARS:
            hi_reg = instr.rs
            found_lui = False
            for j in range(i - 1, max(i - 40, -1), -1):
                prev = instrs[j]
                if prev.opcode == OPCODE_LUI and prev.rt == hi_reg:
                    found_lui = prev.imm == CD_POINTER_HI
                    break
                if _instr_writes_reg(prev) == hi_reg:
                    break  # hi_reg redefined by something else first
            if found_lui:
                addr = CD_POINTER_VARS[instr.imm]
                tags[instr.rt] = RegTag(
                    address=addr, origin_pc=instr.addr,
                    via=f"lui+lw @0x{instr.addr:08X} (var+0x{instr.imm:X})",
                )

        # --- Pattern: ORI $r2,$r,imm where a preceding LUI $r,0x1F80
        # constructs a direct literal CD register address. Same
        # backward-detection reasoning as above.
        if op == OPCODE_ORI:
            hi_reg = instr.rs
            found_lui_1f80 = False
            for j in range(i - 1, max(i - 8, -1), -1):
                prev = instrs[j]
                if prev.opcode == OPCODE_LUI and prev.rt == hi_reg:
                    found_lui_1f80 = prev.imm == 0x1F80
                    break
                if _instr_writes_reg(prev) == hi_reg:
                    break
            if found_lui_1f80:
                full = (0x1F80 << 16) | instr.imm
                if full in CD_POINTER_VARS.values():
                    tags[instr.rt] = RegTag(
                        address=full, origin_pc=instr.addr,
                        via=f"lui+ori @0x{instr.addr:08X} (direct)",
                    )

        # --- Register-copy propagation: addu $rd,$rs,$zero / or $rd,$rs,$zero
        if op == OPCODE_SPECIAL and instr.funct in (FUNCT_ADDU, FUNCT_OR):
            src = instr.rs if instr.rt == 0 else (instr.rt if instr.rs == 0 else None)
            if src is not None and src in tags and src != 0:
                tags[instr.rd] = RegTag(
                    address=tags[src].address, origin_pc=tags[src].origin_pc,
                    via=tags[src].via + f" -> copied @0x{instr.addr:08X}",
                )
                _maybe_kill(tags, instr.rd, keep=True)
                continue  # rd's new tag already set; don't let generic kill logic wipe it

        # --- Small pointer-arithmetic propagation: addiu $rd,$rs,imm (|imm|<=8)
        if op == OPCODE_ADDIU and instr.rs in tags and abs(instr.simm) <= 8:
            base_tag = tags[instr.rs]
            tags[instr.rt] = RegTag(
                address=base_tag.address + instr.simm, origin_pc=base_tag.origin_pc,
                via=base_tag.via + f" -> +{instr.simm} @0x{instr.addr:08X}",
            )
            continue

        # --- Use as load/store base
        if op in LOAD_OPCODES or op in STORE_OPCODES:
            base_reg = instr.rs
            if base_reg in tags:
                tag = tags[base_reg]
                effective = tag.address + instr.simm
                if effective in CD_POINTER_VARS.values():
                    access = AccessType.READ if op in LOAD_OPCODES else AccessType.WRITE
                    sites.append(FifoSite(
                        pc=instr.addr, access=access, effective_addr=effective,
                        instruction_text=_instr_text(instr), pointer_origin_pc=tag.origin_pc,
                        reg=instr.rt, confidence="HIGH", note=tag.via,
                    ))

        # --- Passed to a function call (a0-a3 tagged right before a JAL)
        if op == OPCODE_JAL:
            jal_count += 1
            for reg in (4, 5, 6, 7):
                if reg in tags:
                    sites.append(FifoSite(
                        pc=instr.addr, access=AccessType.ADDRESS_ONLY,
                        effective_addr=tags[reg].address, instruction_text=_instr_text(instr),
                        pointer_origin_pc=tags[reg].origin_pc, reg=reg, confidence="MEDIUM",
                        note=f"passed as arg{reg-4} to call target, not followed cross-function; {tags[reg].via}",
                    ))

        # --- Kill logic: any instruction that writes a GPR without being
        # recognised above as tag-preserving kills that register's tag.
        written = _instr_writes_reg(instr)
        if written is not None and written != 0:
            # the LUI+LW pointer-establish path above already set the
            # correct fresh tag for `written` in the branch that matched;
            # only kill if this specific instruction did NOT just set it.
            just_set_by_lui_lw = (op == OPCODE_LW and instr.imm in CD_POINTER_VARS)
            just_set_by_ori = (op == OPCODE_ORI)
            if not (just_set_by_lui_lw or just_set_by_ori) and written in tags:
                del tags[written]

    functions_estimated = sum(1 for instr in instrs if instr.opcode == OPCODE_JAL)
    return ScanResult(instructions_scanned=len(instrs), functions_estimated=functions_estimated, sites=sites)


def _maybe_kill(tags: dict[int, RegTag], reg: int, keep: bool) -> None:
    if not keep and reg in tags:
        del tags[reg]


def _instr_writes_reg(instr: Instruction) -> int | None:
    op = instr.opcode
    if op in LOAD_OPCODES or op == OPCODE_LUI or op == OPCODE_ORI or op == OPCODE_ADDIU or op == OPCODE_ANDI:
        return instr.rt
    if op == OPCODE_SPECIAL:
        return instr.rd
    return None


def format_report_table(result: ScanResult) -> str:
    lines = ["| PC | Access | Effective HW addr | Instruction | Origin | Confidence |",
             "|---|---|---|---|---|---|"]
    for s in sorted(result.sites, key=lambda x: x.pc):
        lines.append(
            f"| `{s.label}` | {s.access.value} | `0x{s.effective_addr:08X}` | "
            f"`{s.instruction_text}` | {s.note} | {s.confidence} |"
        )
    return "\n".join(lines)
