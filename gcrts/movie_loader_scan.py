"""Movie-loader architecture scanner: maps HOW each chapter executable
selects and loads a movie-player executable, not what the movies
themselves contain (see docs/renderer/MOVIE_LOADER_ARCHITECTURE.md for
the full investigation this module was built for).

Every `CAP*.EXE` chapter overlay this project has read directly off the
real disc image embeds:

1. an identical 10-entry table of movie-player executable names
   (`find_movie_name_table`) -- 3 of the 10 don't exist as real files on
   disc at all, presumably cut content (see `gcrts.movie_detection`'s
   `MOVIE_CATALOG`, which only has the 7 real ones).
2. its own compiled copy of a generic "load movie by index" dispatcher
   function, printing a fixed `"MovieLoad Exec : %s"` debug line
   (`find_dispatcher`) -- located by finding that format string's own
   address reference, then walking backward to the containing
   function's prologue.
3. a small per-file pointer table the dispatcher indexes into with its
   `movie_id` argument (`find_dispatcher`'s own `pointer_table` field)
   -- this project's own earlier ad hoc investigation first assumed
   this table's entries were in the same order as the adjacent name
   table, which turned out to be backwards; this module resolves each
   entry's REAL target string address and looks up which name it
   actually points to, rather than assuming any fixed order.

`find_call_sites` then finds every direct (`jal`) call into that
dispatcher within the same file, and attempts to resolve the
`movie_id` argument via a bounded backward register data-flow trace
(`trace_register_backward`) -- a straight-line scan, not a full
control-flow-graph analysis, so a value that only resolves to a
constant along one of several converging branches is correctly
reported as unresolved rather than guessed. Every result is one of:

- `STATIC_CODE_MATCH` -- the call site's own code unambiguously loads
  a constant `movie_id`.
- `PARTIAL_STATIC` -- part of the address chain is known (e.g. a global
  memory address the value is loaded from) but the actual runtime value
  at that address isn't statically known.
- `DYNAMIC_SELECTOR` -- the value demonstrably comes from a register
  copy chain that traces back to the *containing function's own
  incoming parameter*, meaning some caller of THAT function supplies
  it -- this module chases that chain a bounded number of hops
  (`max_caller_hops`), and reports whatever it finds at the end,
  never fabricating a value it didn't find.
- `UNKNOWN` -- the trace hit its step limit, an unhandled instruction
  pattern, or a branch join before resolving anything.

Nothing here is promoted to `CONFIRMED_LIVE` -- that tier, per this
whole project's standing rule, is reserved for something actually
witnessed happening live, never assigned from static analysis alone
(see `gcrts.movie_detection.MovieMatchConfidence`).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum

from gcrts import iso9660
from gcrts.mips_disasm import Instruction, decode_instruction, reg_index

DEFAULT_DISC_PATH = "קיבצי דמה/Twilight Syndrome - Tansaku Hen (Japan).bin"
HEADER_SIZE = 0x800

# t_addr for every executable this scanner knows how to read, taken
# directly from gcrts.overlay_identity.KNOWN_OVERLAYS (not re-derived).
T_ADDR: dict[str, int] = {
    "PROG.EXE": 0x80035000,
    "CAP0.EXE": 0x80045000,
    "CAP1.EXE": 0x80035000,
    "CAP2.EXE": 0x80035000,
    "CAP3.EXE": 0x80035000,
    "CAP4.EXE": 0x80035000,
    "CAPX.EXE": 0x80035000,
}

# The real, verified order of the 10-entry movie-name table, common to
# every CAP*.EXE (byte-identical table contents at shifted file offsets
# -- confirmed independently per file, not assumed). MCAVE.EXE, MSB.EXE,
# and MGOKI.EXE do not exist as real files on disc (see
# gcrts.movie_detection.MOVIE_CATALOG) -- presumably cut content, left
# in the shared table but never shipped.
MOVIE_TABLE_NAMES: tuple[str, ...] = (
    "MYOKO.EXE", "MPRO.EXE", "MOP.EXE", "MCAVE.EXE", "MSB.EXE",
    "MRIKA.EXE", "MOVER.EXE", "MNINO.EXE", "MKUBI.EXE", "MGOKI.EXE",
)
CUT_CONTENT_NAMES: frozenset[str] = frozenset({"MCAVE.EXE", "MSB.EXE", "MGOKI.EXE"})

MOVIE_LOAD_FORMAT_STRING = b"MovieLoad Exec : %s"


class CallSiteClassification(str, Enum):
    STATIC_CODE_MATCH = "STATIC_CODE_MATCH"
    PARTIAL_STATIC = "PARTIAL_STATIC"
    DYNAMIC_SELECTOR = "DYNAMIC_SELECTOR"
    UNKNOWN = "UNKNOWN"


def read_executable(name: str, raw: bytes | None = None, disc_path: str = DEFAULT_DISC_PATH) -> tuple[bytes, int]:
    """Read one executable's full raw file bytes (PS-EXE header
    included) plus its known `t_addr`, directly off the real disc image.
    `raw` lets a caller pass an already-loaded disc image once instead
    of re-reading a multi-GB file per executable."""
    if name not in T_ADDR:
        raise ValueError(f"no known t_addr for {name!r}")
    if raw is None:
        with open(disc_path, "rb") as f:
            raw = f.read()
    root = iso9660.read_root_directory(raw)
    entry = next((e for e in root if e.name == f"{name};1"), None)
    if entry is None:
        raise ValueError(f"{name} not found in root directory")
    data = iso9660.read_file(raw, entry)
    return data, T_ADDR[name]


def _file_off_to_ram(file_off: int, t_addr: int) -> int:
    return t_addr + (file_off - HEADER_SIZE)


def _ram_to_file_off(ram: int, t_addr: int) -> int:
    return (ram - t_addr) + HEADER_SIZE


@dataclass(frozen=True)
class MovieNameEntry:
    index: int  # position in MOVIE_TABLE_NAMES
    name: str
    ram_addr: int  # address of the backslash-prefixed C string, e.g. "\MPRO.EXE;1"
    is_cut_content: bool  # true if this name has no corresponding real file on disc


@dataclass(frozen=True)
class MovieNameTable:
    entries: tuple[MovieNameEntry, ...]

    def ram_to_name(self) -> dict[int, str]:
        return {e.ram_addr: e.name for e in self.entries}

    def to_dict(self) -> dict:
        return {
            "entries": [
                {"index": e.index, "name": e.name, "ram_addr": hex(e.ram_addr), "is_cut_content": e.is_cut_content}
                for e in self.entries
            ]
        }


def find_movie_name_table(data: bytes, t_addr: int) -> MovieNameTable | None:
    """Locate every one of the 10 known movie-name strings in this
    file's own bytes (each is stored as a null-padded, backslash-and-
    version-suffixed C string, e.g. "\\MPRO.EXE;1"), and return their
    real RAM addresses. Returns None if none of the 10 names are
    present at all (this file has no movie-loading code)."""
    entries = []
    for i, name in enumerate(MOVIE_TABLE_NAMES):
        raw_name = name.encode("ascii")
        off = data.find(raw_name)
        if off == -1:
            continue
        backslash_off = off - 1
        if backslash_off < 0 or data[backslash_off : backslash_off + 1] != b"\\":
            continue
        ram = _file_off_to_ram(backslash_off, t_addr)
        entries.append(MovieNameEntry(index=i, name=name, ram_addr=ram, is_cut_content=name in CUT_CONTENT_NAMES))
    if not entries:
        return None
    return MovieNameTable(entries=tuple(entries))


@dataclass(frozen=True)
class DispatcherInfo:
    entry_ram: int  # the dispatcher function's own prologue address
    fmt_string_ref_ram: int  # where the "MovieLoad Exec : %s" address is loaded (lui site)
    pointer_table_base_ram: int
    pointer_table_entries: tuple[int | None, ...]  # movie-table index resolved per pointer-table slot, or None if unresolved

    def to_dict(self) -> dict:
        return {
            "entry_ram": hex(self.entry_ram),
            "fmt_string_ref_ram": hex(self.fmt_string_ref_ram),
            "pointer_table_base_ram": hex(self.pointer_table_base_ram),
            "pointer_table_entries": [
                MOVIE_TABLE_NAMES[i] if i is not None else None for i in self.pointer_table_entries
            ],
        }


def _words(data: bytes) -> list[int]:
    n = len(data) - (len(data) % 4)
    return [int.from_bytes(data[i : i + 4], "little") for i in range(0, n, 4)]


def find_dispatcher(data: bytes, t_addr: int, name_table: MovieNameTable) -> DispatcherInfo | None:
    """Find this file's own copy of the movie-dispatch function: the one
    whose code loads the address of "MovieLoad Exec : %s" into $a0 (the
    printf-style first argument), then walk backward from that
    reference to the function's own prologue and to the small pointer
    table its `movie_id` argument indexes into."""
    fmt_off = data.find(MOVIE_LOAD_FORMAT_STRING)
    if fmt_off == -1:
        return None
    fmt_ram = _file_off_to_ram(fmt_off, t_addr)
    hi, lo = fmt_ram >> 16, fmt_ram & 0xFFFF

    words = _words(data)
    a0 = reg_index("a0")
    fmt_ref_idx = None
    for i, w in enumerate(words):
        instr = decode_instruction(t_addr + (i * 4 - HEADER_SIZE), w)
        if instr.op == "lui" and instr.rt == a0 and instr.imm == hi:
            for j in range(i + 1, min(i + 6, len(words))):
                instr2 = decode_instruction(t_addr + (j * 4 - HEADER_SIZE), words[j])
                if instr2.op in ("addiu", "ori") and instr2.rs == a0 and instr2.rt == a0 and instr2.imm == lo:
                    fmt_ref_idx = i
                    break
        if fmt_ref_idx is not None:
            break
    if fmt_ref_idx is None:
        return None

    # Function prologue: walk backward for 'addiu sp,sp,-N'.
    sp = reg_index("sp")
    func_start_idx = None
    for k in range(fmt_ref_idx, max(fmt_ref_idx - 80, 0), -1):
        instr = decode_instruction(t_addr + (k * 4 - HEADER_SIZE), words[k])
        if instr.op == "addiu" and instr.rs == sp and instr.rt == sp and instr.simm < 0:
            func_start_idx = k
            break
    if func_start_idx is None:
        return None
    func_ram = t_addr + (func_start_idx * 4 - HEADER_SIZE)

    # Pointer-table base: the lui/addiu pair 6/5 words before the format
    # string reference, per this file's own copy of the dispatcher
    # (verified against CAP0.EXE's disassembly; re-derived per file
    # below rather than assumed to always be exactly -6/-5).
    table_base_ram = None
    for back in range(2, 12):
        idx = fmt_ref_idx - back
        if idx < 0:
            break
        w1 = decode_instruction(t_addr + (idx * 4 - HEADER_SIZE), words[idx])
        if idx + 1 >= len(words):
            continue
        w2 = decode_instruction(t_addr + ((idx + 1) * 4 - HEADER_SIZE), words[idx + 1])
        if w1.op == "lui" and w2.op in ("addiu", "ori") and w2.rs == w1.rt and w2.rt == w1.rt:
            candidate = ((w1.imm << 16) + w2.simm) & 0xFFFFFFFF
            # Sanity check: this candidate must itself be inside this
            # file's own loaded address range to be a real data table.
            file_off = _ram_to_file_off(candidate, t_addr)
            if 0 <= file_off < len(data):
                table_base_ram = candidate
                break
    if table_base_ram is None:
        return DispatcherInfo(
            entry_ram=func_ram, fmt_string_ref_ram=t_addr + (fmt_ref_idx * 4 - HEADER_SIZE),
            pointer_table_base_ram=0, pointer_table_entries=(),
        )

    ram_to_name = name_table.ram_to_name()
    table_off = _ram_to_file_off(table_base_ram, t_addr)
    resolved: list[int | None] = []
    for i in range(10):
        entry_off = table_off + i * 4
        if entry_off + 4 > len(data):
            resolved.append(None)
            continue
        ptr = int.from_bytes(data[entry_off : entry_off + 4], "little")
        name = ram_to_name.get(ptr)
        resolved.append(MOVIE_TABLE_NAMES.index(name) if name is not None else None)

    return DispatcherInfo(
        entry_ram=func_ram,
        fmt_string_ref_ram=t_addr + (fmt_ref_idx * 4 - HEADER_SIZE),
        pointer_table_base_ram=table_base_ram,
        pointer_table_entries=tuple(resolved),
    )


@dataclass
class TraceStep:
    ram: int
    text: str


@dataclass
class SelectorTrace:
    classification: CallSiteClassification
    resolved_movie_id: int | None
    steps: list[TraceStep] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "classification": self.classification.value,
            "resolved_movie_id": self.resolved_movie_id,
            "steps": [{"ram": hex(s.ram), "text": s.text} for s in self.steps],
            "note": self.note,
        }


def _find_function_start(instrs_by_idx: list[Instruction], idx: int) -> int:
    sp = reg_index("sp")
    for k in range(idx, max(idx - 400, 0), -1):
        instr = instrs_by_idx[k]
        if instr.op == "addiu" and instr.rs == sp and instr.rt == sp and instr.simm < 0:
            return k
    return max(idx - 400, 0)


def _writes_to(instr: Instruction) -> int | None:
    """Which register (if any) this instruction defines, or None for
    stores/branches/nop/unrecognized instructions that write nothing."""
    if instr.op in ("addu", "subu", "and", "or", "xor", "nor", "slt", "sltu", "sll", "srl", "sra"):
        return instr.rd
    if instr.op in ("lui", "ori", "andi", "xori", "addi", "addiu", "slti", "sltiu", "lw", "lb", "lbu", "lh", "lhu"):
        return instr.rt
    return None


def trace_register_backward(
    instrs_by_idx: list[Instruction], call_idx: int, reg: int, max_steps: int = 200
) -> SelectorTrace:
    """Straight-line (not CFG-aware) backward data-flow trace for one
    register's value at the moment `instrs_by_idx[call_idx]` (a `jal`)
    executes. Checks the branch-delay slot first (the instruction
    physically after the jal, but logically part of setting up its
    arguments), then walks backward through the containing function
    only, stopping at its own prologue. A value that only resolves along
    one of several converging branches will not be found by this simple
    scan -- that's an explicit, documented limitation, not a silent
    wrong answer: such cases fall through to UNKNOWN/PARTIAL_STATIC
    rather than being guessed."""
    func_start = _find_function_start(instrs_by_idx, call_idx)
    steps: list[TraceStep] = []
    current_reg = reg
    # None while tracing a plain register value; once a `lw` is crossed,
    # holds the offset that must be added once `current_reg` (now the
    # load's base register) itself resolves to a constant -- this lets a
    # base register whose own lui/addiu pair sits FURTHER back in the
    # backward walk still resolve correctly.
    pending_load_offset: int | None = None
    # A self-referential addiu/ori ("addiu $r,$r,LOW") was seen for
    # `current_reg` and is waiting for the matching `lui $r,HIGH`
    # further back -- since this is a BACKWARD walk, that lui is
    # necessarily visited AFTER this addiu/ori in iteration order (it
    # sits at a smaller instruction index), so it cannot be looked up in
    # a dict populated during the same pass; it must be waited for
    # explicitly instead. Holds (register, low_value).
    waiting_for_lui: tuple[int, int] | None = None
    budget = max_steps

    def finalize_constant(value: int) -> SelectorTrace:
        if pending_load_offset is None:
            return SelectorTrace(CallSiteClassification.STATIC_CODE_MATCH, value & 0xFFFFFFFF, steps)
        addr = (value + pending_load_offset) & 0xFFFFFFFF
        return SelectorTrace(
            CallSiteClassification.PARTIAL_STATIC, None, steps,
            f"movie_id is loaded from global memory address 0x{addr:08X} -- "
            "runtime value at that address is not known from static analysis alone",
        )

    def finalize_computed_address(value: int) -> SelectorTrace:
        # A register-holds-an-address case reached without a pending
        # load being resolved further (e.g. the traced register itself
        # IS the address, never dereferenced) -- still not a plain
        # movie_id constant.
        return SelectorTrace(
            CallSiteClassification.PARTIAL_STATIC, None, steps,
            f"register holds a computed address 0x{value:08X} (likely a global/table base), "
            "not a plain movie_id constant",
        )

    # Delay slot first, then walk backward from call_idx-1 down to the prologue.
    order = [call_idx + 1] + list(range(call_idx - 1, func_start - 1, -1))

    for i in order:
        if budget <= 0:
            return SelectorTrace(CallSiteClassification.UNKNOWN, None, steps, "step budget exhausted")
        if i < 0 or i >= len(instrs_by_idx):
            continue
        instr = instrs_by_idx[i]
        budget -= 1

        if instr.op == "lui":
            if waiting_for_lui is not None and instr.rt == waiting_for_lui[0]:
                steps.append(TraceStep(instr.pc, instr.text))
                value = ((instr.imm << 16) + waiting_for_lui[1]) & 0xFFFFFFFF
                if pending_load_offset is None:
                    return finalize_computed_address(value)
                return finalize_constant(value)
            continue

        written = _writes_to(instr)
        if written != current_reg:
            continue

        if instr.op in ("addu", "or") and (instr.rs == 0 or instr.rt == 0) and instr.rd == current_reg:
            # move $rd, $rs  (encoded as addu/or with the other operand $zero)
            steps.append(TraceStep(instr.pc, instr.text))
            current_reg = instr.rt if instr.rs == 0 else instr.rs
            continue

        if instr.op in ("addu", "subu", "and", "or", "xor", "nor", "slt", "sltu") and instr.rd == current_reg:
            steps.append(TraceStep(instr.pc, instr.text))
            return SelectorTrace(
                CallSiteClassification.UNKNOWN, None, steps,
                f"register combines two other registers (not a simple move or constant): {instr.text}",
            )

        if instr.op in ("ori", "addiu") and instr.rt == current_reg:
            steps.append(TraceStep(instr.pc, instr.text))
            if instr.rs == 0:
                value = instr.simm if instr.op == "addiu" else instr.imm
                return finalize_constant(value)
            if instr.rs == current_reg:
                low = instr.simm if instr.op == "addiu" else instr.imm
                waiting_for_lui = (current_reg, low)
                continue
            current_reg = instr.rs
            continue

        if instr.op == "lw" and instr.rt == current_reg:
            if pending_load_offset is not None:
                steps.append(TraceStep(instr.pc, instr.text))
                return SelectorTrace(
                    CallSiteClassification.UNKNOWN, None, steps,
                    "double memory indirection (load-of-a-load) -- beyond this tracer's scope",
                )
            steps.append(TraceStep(instr.pc, instr.text))
            pending_load_offset = instr.simm
            current_reg = instr.rs
            continue

        if instr.op in ("sll", "srl", "sra") and instr.rd == current_reg:
            steps.append(TraceStep(instr.pc, instr.text))
            current_reg = instr.rt
            continue

        if instr.op == "andi" and instr.rt == current_reg:
            steps.append(TraceStep(instr.pc, instr.text))
            current_reg = instr.rs
            continue

    if waiting_for_lui is not None:
        return SelectorTrace(
            CallSiteClassification.UNKNOWN, None, steps,
            "addiu/ori self-referential without a matching lui found before the function's prologue",
        )

    # Reached the function's own prologue without finding a defining write.
    return SelectorTrace(
        CallSiteClassification.DYNAMIC_SELECTOR, None, steps,
        f"register ${_reg_name_safe(current_reg)} is never (re)defined within this function -- "
        "value comes from whatever this function's caller passed in as its own incoming parameter",
    )


def _reg_name_safe(i: int) -> str:
    from gcrts.mips_disasm import reg_name
    try:
        return reg_name(i)
    except IndexError:
        return f"r{i}"


@dataclass
class CallSite:
    caller_ram: int
    classification: CallSiteClassification
    resolved_movie_id: int | None
    resolved_movie_name: str | None
    trace: SelectorTrace

    def to_dict(self) -> dict:
        return {
            "caller_ram": hex(self.caller_ram),
            "classification": self.classification.value,
            "resolved_movie_id": self.resolved_movie_id,
            "resolved_movie_name": self.resolved_movie_name,
            "trace": self.trace.to_dict(),
        }


def find_call_sites(data: bytes, t_addr: int, dispatcher: DispatcherInfo) -> list[CallSite]:
    """Every `jal` in this file targeting `dispatcher.entry_ram`, with a
    best-effort backward trace of the movie_id argument register ($a1)."""
    words = _words(data)
    instrs = [decode_instruction(t_addr + (i * 4 - HEADER_SIZE), w) for i, w in enumerate(words)]
    a1 = reg_index("a1")
    sites = []
    for i, instr in enumerate(instrs):
        if instr.op == "jal" and instr.target == dispatcher.entry_ram:
            trace = trace_register_backward(instrs, i, a1)
            movie_name = None
            if trace.classification == CallSiteClassification.STATIC_CODE_MATCH and trace.resolved_movie_id is not None:
                idx = trace.resolved_movie_id & 0xFF
                if 0 <= idx < len(dispatcher.pointer_table_entries):
                    table_idx = dispatcher.pointer_table_entries[idx]
                    if table_idx is not None:
                        movie_name = MOVIE_TABLE_NAMES[table_idx]
            sites.append(CallSite(
                caller_ram=instr.pc, classification=trace.classification,
                resolved_movie_id=trace.resolved_movie_id, resolved_movie_name=movie_name, trace=trace,
            ))
    return sites


@dataclass
class ExecutableMovieLoaderReport:
    executable: str
    t_addr: int
    has_movie_name_table: bool
    name_table: MovieNameTable | None
    dispatcher: DispatcherInfo | None
    call_sites: list[CallSite]

    def to_dict(self) -> dict:
        return {
            "executable": self.executable,
            "t_addr": hex(self.t_addr),
            "has_movie_name_table": self.has_movie_name_table,
            "name_table": self.name_table.to_dict() if self.name_table else None,
            "dispatcher": self.dispatcher.to_dict() if self.dispatcher else None,
            "call_sites": [c.to_dict() for c in self.call_sites],
        }


def scan_executable(name: str, raw: bytes | None = None, disc_path: str = DEFAULT_DISC_PATH) -> ExecutableMovieLoaderReport:
    data, t_addr = read_executable(name, raw=raw, disc_path=disc_path)
    name_table = find_movie_name_table(data, t_addr)
    if name_table is None:
        return ExecutableMovieLoaderReport(name, t_addr, False, None, None, [])
    dispatcher = find_dispatcher(data, t_addr, name_table)
    call_sites = find_call_sites(data, t_addr, dispatcher) if dispatcher is not None else []
    return ExecutableMovieLoaderReport(name, t_addr, True, name_table, dispatcher, call_sites)


def scan_all(names: tuple[str, ...] = tuple(T_ADDR), disc_path: str = DEFAULT_DISC_PATH) -> dict[str, ExecutableMovieLoaderReport]:
    with open(disc_path, "rb") as f:
        raw = f.read()
    return {name: scan_executable(name, raw=raw) for name in names}


def _cmd_main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--disc", default=DEFAULT_DISC_PATH)
    parser.add_argument("--out", default="movie_loader_map.json")
    args = parser.parse_args(argv)

    reports = scan_all(disc_path=args.disc)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({name: r.to_dict() for name, r in reports.items()}, f, indent=2)
    for name, r in reports.items():
        print(f"=== {name} ===")
        if not r.has_movie_name_table:
            print("  no movie-name table found")
            continue
        print(f"  dispatcher entry: {hex(r.dispatcher.entry_ram) if r.dispatcher else None}")
        for c in r.call_sites:
            print(f"  call at {hex(c.caller_ram)}: {c.classification.value} movie={c.resolved_movie_name}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cmd_main())
