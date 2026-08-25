# Movie-Loader Architecture

Scope: **how the game decides which movie executable to load**, not
what the movies contain. This document is the full write-up of a
dedicated static/runtime investigation into that question, using the
new `gcrts.mips_disasm` (general MIPS-I decoder) and
`gcrts.movie_loader_scan` (the reusable scanner built on top of it).
Everything here is either read directly off the real disc image, or a
live GDB observation against the real emulator -- no content of any
movie itself was inspected.

## 1. Executive summary

Every `CAP*.EXE` chapter executable (`CAP0`-`CAP4`, `CAPX`) embeds an
**identical** 10-entry table of movie-player executable names and its
own compiled copy of one generic "print + load movie by index"
function. A chapter selects a movie by calling that function with a
small integer index (`movie_id`, 0-9) in `$a1`; the function masks it
to a byte, multiplies by 4, indexes a small local pointer table to get
the movie's filename string address, prints a debug line
(`"MovieLoad Exec : %s"`), and hands the string to the real CD-EXEC
loader.

For four chapters (`CAP0`, `CAP1`, `CAP4` twice, `CAPX`), that index is
a **hardcoded compile-time constant** -- found by scanning each
chapter's own code for calls into its dispatcher with an immediate
value in the branch-delay slot. `CAP2.EXE` and `CAP3.EXE` have zero
such calls; either they don't trigger a movie this way, or (like an
initial hypothesis about `CAPX.EXE`, since disproven) they use a
selector this static method can't resolve.

**A wrong hypothesis was made and then corrected mid-investigation.**
An earlier console-log capture showed `CAPX.EXE` resident near the
moment `MPRO.EXE`'s load printed, which led to the (wrong) idea that
`CAP0.EXE` "hands off" to `CAPX.EXE` to perform chapter transitions'
actual movie loads. Direct live testing disproved this: a GDB
breakpoint at `CAP0.EXE`'s own dispatcher fired immediately on a real
save-slot-6 load, with `$a1` read live as exactly `8` (`MPRO.EXE`) and
the live pointer-table bytes matching the disc exactly; a breakpoint at
`CAPX.EXE`'s own dispatcher, armed for the same scenario, never fired
at all despite the movie fully loading and playing. **`CAPX.EXE` plays
no part in `CAP0.EXE`'s movie load.** The simplest reading consistent
with all evidence is that `CAPX.EXE` is just another regular chapter,
like `CAP0`-`CAP4`, with its own dedicated (and so far untested)
movie trigger -- not a shared front-end other chapters route through.

## 2. Movie loader reconstruction

Real disassembly of `CAP0.EXE`'s copy (RAM `0x8006E5E4`), annotated:

```c
// void load_movie(void *context /* $a0 */, int movie_id /* $a1 */)
void load_movie(Context *context, int movie_id) {
    Context *ctx = context;                       // addu $s1, $a0, $zero
    int index = movie_id & 0xFF;                   // andi $s0, $a1, 0xFF
    char **table = (char **)0x8009C514;             // lui/addiu $v0
    char *name = table[index];                      // sll $s0,$s0,2; addu; lw $a1,0($s0)
    printf("MovieLoad Exec : %s", name);             // lui/addiu $a0; jal 0x80077F68
    some_pre_load_setup(ctx);                        // jal 0x8006E6E4 (unexplored)
    other_setup_call();                              // jal 0x80083ED8
    yet_another_setup_call();                        // jal 0x8008270C
    bool ok = perform_exec_load(name);               // jal 0x8006E76C (the real CD loader)
    if (!ok) {
        printf("MovieLoad Exec Error!!");            // fallback error string, same table region
    }
}
```

- **Parameters**: `$a0` = an opaque context pointer (saved to `$s1`,
  used later for the setup calls; never inspected further -- out of
  scope per this investigation's own charter), `$a1` = `movie_id`
  (0-9, masked to a byte before use, so any value outside that range
  simply wraps).
- **Globals referenced**: the local pointer table (`0x8009C514` for
  `CAP0.EXE` specifically -- a different address per file, see
  Investigation 2) and the two fixed debug/format strings.
- **Return value**: none meaningful to the caller observed (the
  function's own internal error branch just prints a different debug
  string; nothing is returned to indicate success/failure to the
  chapter code that called it).
- **Binary-identical across chapters?** The *table layout and dispatch
  logic* are identical (verified independently per file -- see
  Investigation 2's table). The *function's own address* differs per
  file (different `t_addr`, different surrounding code), and so does
  the *set of calls made after the print* only in that they target
  different local addresses -- their actual behavior wasn't
  independently disassembled per file (out of scope: those are the
  "unexplored setup calls," not part of movie selection itself).

## 3. Canonical movie-name table

Real order (index 0-9), confirmed identical across all 6 chapter files
independently (each file's own pointer table was read and its entries
resolved against that same file's own string addresses -- not assumed
to match any other file):

| Index | Filename | Real file on disc? |
|---:|---|---|
| 0 | `MYOKO.EXE` | yes |
| 1 | `MPRO.EXE` | yes |
| 2 | `MOP.EXE` | yes |
| 3 | `MCAVE.EXE` | **no** -- cut content |
| 4 | `MSB.EXE` | **no** -- cut content |
| 5 | `MRIKA.EXE` | yes |
| 6 | `MOVER.EXE` | yes |
| 7 | `MNINO.EXE` | yes |
| 8 | `MKUBI.EXE` | yes |
| 9 | `MGOKI.EXE` | **no** -- cut content |

Entries are **inline C strings**, not just filenames referenced by
pointer alone at the *name-table* level -- each is stored as
`"\NAME.EXE;1\0"` (backslash-prefixed, ISO9660-version-suffixed, null-
padded to a 16-byte boundary). The *pointer table* the dispatcher
actually indexes is a separate, small array of 4-byte pointers into
these strings -- and that array's order is **reversed** relative to
the string table above (`pointer_table[0]` points at index-9's string,
`MGOKI.EXE`; `pointer_table[9]` points at index-0's string, `MYOKO.EXE`).
This reversal was the first of two assumptions this investigation
caught and corrected before trusting a result (see §12).

Per-file table/name addresses (real, read directly off disc):

| Executable | t_addr | Name-table base (≈) | Pointer-table base |
|---|---|---|---|
| `CAP0.EXE` | `0x80045000` | `0x80046284` | `0x8009C514` |
| `CAP1.EXE` | `0x80035000` | (per-file, not restated) | `0x8009B164` |
| `CAP2.EXE` | `0x80035000` | (per-file, not restated) | `0x8009714C` |
| `CAP3.EXE` | `0x80035000` | (per-file, not restated) | `0x8009BE40` |
| `CAP4.EXE` | `0x80035000` | (per-file, not restated) | `0x8009BF9C` |
| `CAPX.EXE` | `0x80035000` | (per-file, not restated) | `0x8008C04C` |

(Every file's exact 10 string addresses and its dispatcher entry
address are in `movie_loader_map.json`, regenerable via
`python -m gcrts.movie_loader_scan`.)

`PROG.EXE` has **no** movie-name table and **no** copy of the dispatch
string at all -- confirmed by direct search, not merely "not yet
checked." It plays no role in movie selection.

## 4. All call sites (`gcrts.movie_loader_scan.find_call_sites`)

Every direct (`jal`) call in each file targeting that file's own
dispatcher entry, with the `movie_id` argument backward-traced:

| Executable | Call site | movie_id | Movie | Classification |
|---|---|---:|---|---|
| `CAP0.EXE` | `0x8006CCB0` | 8 | `MPRO.EXE` | `CONFIRMED_LIVE` (see §5) |
| `CAP1.EXE` | `0x8005DBE4` | 1 | `MKUBI.EXE` | `STATIC_CODE_MATCH` |
| `CAP1.EXE` | `0x8005E700` | 1 | `MKUBI.EXE` | `STATIC_CODE_MATCH` |
| `CAP4.EXE` | `0x8004CB00` | 4 | `MRIKA.EXE` | `STATIC_CODE_MATCH` |
| `CAP4.EXE` | `0x8005033C` | 2 | `MNINO.EXE` | `STATIC_CODE_MATCH` |
| `CAPX.EXE` | `0x80041234` | 9 | `MYOKO.EXE` | `STATIC_CODE_MATCH`, untested live |
| `CAP2.EXE` | -- | -- | -- | no call sites found at all |
| `CAP3.EXE` | -- | -- | -- | no call sites found at all |

No call site in any file resolved to `DYNAMIC_SELECTOR` or
`PARTIAL_STATIC` -- every *direct* call found is a plain hardcoded
constant. `CAP2.EXE`/`CAP3.EXE` having zero call sites is a different
situation from a resolved-but-dynamic one: it means no code anywhere in
those files calls this specific dispatcher function at all, direct or
otherwise (checked for indirect calls too, see §5's method, applied the
same way to these files with the same negative result).

## 5. CAPX.EXE investigation

This was the focus of the live-verification phase, since it's the file
that produced the apparent contradiction.

**What was checked:**
1. All direct `jal` calls to `CAPX.EXE`'s own dispatcher entry
   (`0x80062018`) in its own code: exactly one, at `0x80041234`,
   hardcoded `movie_id=9` (`MYOKO.EXE`).
2. All 215 `jalr` (register-indirect call) sites in the whole file:
   none load the dispatcher's exact address (`0x80062018`) as a
   constant anywhere beforehand (checked every `lui`+`addiu`/`ori` pair
   in the file for that literal target value -- zero matches).
3. Whether that exact address appears anywhere as *raw data* (e.g. a
   function-pointer table entry read by an indirect call): searched
   the whole file's raw bytes for the little-endian 4-byte value
   `0x80062018` -- zero occurrences.
4. Whether the dispatcher's own format string has a second reference
   anywhere in the file (would indicate either a second call site or
   an inlined duplicate): exactly one literal copy of the string, one
   `lui`/`addiu` pair referencing it, both already covered by point 1.
5. **Direct live test**: armed a GDB breakpoint at `CAPX.EXE`'s
   dispatcher entry (`0x80062018`) and reloaded the real save state
   (slot 6) known to trigger `MPRO.EXE`. The breakpoint **never fired**
   across a 30-second window, even though the console text showed the
   movie fully load (`"MovieLoad Exec : \MPRO.EXE;1"`, `EXEC!`,
   `ResetGraph`) and continue playing (`"waring:old type streaming mode
   in CdRead2"`).

**Conclusion**: `CAPX.EXE`'s dispatcher function is provably *not*
executed during the `CAP0.EXE`→`MPRO.EXE` scenario. There is no
evidence anywhere in `CAPX.EXE`'s own code of a second path into its
dispatcher (direct, indirect, or data-table-driven) that this
investigation's checks could have missed but didn't find. The
resolution to the original "contradiction" is that there wasn't a
real contradiction to begin with -- `CAP0.EXE` never handed off to
`CAPX.EXE`; the two events (a `"Load Exec : \CAPX.EXE;1"` line and this
movie's trigger) that appeared near each other in one long scrolling
console capture were unrelated. `CAPX.EXE`'s own single call site
(`movie_id=9` → `MYOKO.EXE`) is a plausible, ordinary chapter-specific
trigger, structurally identical to `CAP0`/`CAP1`/`CAP4`'s own -- just
not yet independently live-tested, since no existing save state sits
resident in `CAPX.EXE` (all 10 checked land in `PROG.EXE`, `CAP0.EXE`,
`CAP1.EXE`, or `CAP2.EXE`; none in `CAPX.EXE`).

Answering the specific sub-questions asked:

1. **Which callers reach it?** Only its own one hardcoded call site was
   found reachable by any method tried; no other chapter file's code
   calls into `CAPX.EXE`'s dispatcher (they can't -- it's a different
   loaded executable at a different time, not a shared library).
2. **What arguments do they pass?** `movie_id=9`, a plain constant.
3. **Is the selection value overwritten?** No overwrite mechanism
   found; there is no second write to the argument path between the
   constant load and the call.
4. **A global current-movie variable?** None found referenced by
   `CAPX.EXE`'s dispatcher or its one caller.
5. **Does CAPX receive a value from the previous chapter executable?**
   No -- disproven for the one scenario tested; no general mechanism
   for this was found anywhere (see §7).
6. **Shared RAM structure during transition?** None found (see §7).
7. **Does CAPX load from saved state/event state?** Not for this
   call site -- it's a plain immediate constant, not a memory load.
8. **Is the hardcoded call on only one branch?** It's `CAPX.EXE`'s only
   found call site at all; whether reaching it depends on some earlier
   branch within its own containing function wasn't traced further
   (out of scope beyond confirming the constant itself is
   unconditional once that function is entered -- MIPS delay-slot
   semantics guarantee the immediate load happens whenever this
   specific `jal` executes, regardless of how control got there).
9. **Multiple entry points into CAPX's movie subsystem?** None found
   (see checks 1-4 above).
10. **Can a runtime selector bypass the hardcoded call?** No evidence
    either way was found -- the honest answer is "untested," since no
    scenario that resides in `CAPX.EXE` has been reached live yet.

## 6. Runtime selector / data-flow findings

`trace_register_backward` (in `gcrts.movie_loader_scan`) is a bounded,
straight-line (not control-flow-graph-aware) backward data-flow engine.
Given every call site found this session resolved to a plain
hardcoded constant, there is currently no real `DYNAMIC_SELECTOR` or
`PARTIAL_STATIC` case to report from the disc's own `CAP*.EXE` files --
that is itself a finding, not an omission: **every reachable static
call site among these six files passes its target as a compile-time
constant.** The tracer's `PARTIAL_STATIC` (value loaded from a
resolvable global address) and `DYNAMIC_SELECTOR` (value is the
containing function's own unresolved incoming parameter) paths are
implemented and unit-tested (`tests/test_movie_loader_scan.py`) against
synthetic cases mirroring the real patterns found elsewhere in this
project's disassembly, ready to classify a genuinely dynamic call site
the moment one is found (e.g. in `CAP2.EXE`/`CAP3.EXE`, if their
selection mechanism turns out to route through some other, not-yet-
located function this scan didn't check).

## 7. Executable handoff architecture

No shared movie-request structure, no persisted selector variable
across an EXEC-load boundary, and no chapter→`CAPX.EXE` handoff of a
pending movie ID were found -- each was actively searched for, not
assumed absent:

- No constant matching `CAPX.EXE`'s dispatcher address appears
  anywhere in `CAP0.EXE`'s own compiled bytes (checked the same way as
  §5's search, run in the other direction).
- The live breakpoint test in §5 is direct proof against the
  specific "`CAP0.EXE` sets a pending movie, then EXECs into `CAPX.EXE`
  which reads it" model for the one scenario available to test.
- General EXEC-load semantics on this platform: `Load Exec`/
  `MovieLoad Exec` are both printed by what appears to be the same
  shared BIOS/kernel-level `EXEC()` wrapper (identical trace format
  across `PROG.EXE`, every `CAP*.EXE`, and the movie-player family) --
  a normal `EXEC()` call does not, on real PS1 hardware, preserve
  arbitrary CPU register or memory state into the newly-loaded
  executable's own address space beyond whatever the BIOS itself
  reserves; nothing project-specific was found that overrides this.

**Conclusion on the hypothesized handoff model:**

```text
CAP0
  |
  v
set movie = MPRO     <-- NOT FOUND: no write to any address CAPX.EXE reads
  |
  v
request CAPX          <-- NOT FOUND: CAP0.EXE's MPRO.EXE call never loads CAPX.EXE
  |
  v
CAPX reads pending movie   <-- NOT FOUND: no such read exists in CAPX.EXE
  |
  v
load MPRO
```

This model is **rejected**, not assumed. `CAP0.EXE` loads `MPRO.EXE`
directly, using its own copy of the generic dispatcher, with no
executable handoff involved at all.

## 8. Full static movie map

| Executable | Call site | Selector source | movie_id | Movie | Confidence |
|---|---|---|---:|---|---|
| `CAP0.EXE` | `0x8006CCB0` | hardcoded constant | 8 | `MPRO.EXE` | `CONFIRMED_LIVE` |
| `CAP1.EXE` | `0x8005DBE4` | hardcoded constant | 1 | `MKUBI.EXE` | `STATIC_CODE_MATCH` |
| `CAP1.EXE` | `0x8005E700` | hardcoded constant | 1 | `MKUBI.EXE` | `STATIC_CODE_MATCH` |
| `CAP4.EXE` | `0x8004CB00` | hardcoded constant | 4 | `MRIKA.EXE` | `STATIC_CODE_MATCH` |
| `CAP4.EXE` | `0x8005033C` | hardcoded constant | 2 | `MNINO.EXE` | `STATIC_CODE_MATCH` |
| `CAPX.EXE` | `0x80041234` | hardcoded constant | 9 | `MYOKO.EXE` | `STATIC_CODE_MATCH` (untested live) |
| `CAP2.EXE` | -- | none found | -- | -- | `UNKNOWN` |
| `CAP3.EXE` | -- | none found | -- | -- | `UNKNOWN` |
| `MOP.EXE` (via `identify_overlay()` residency, not this scanner) | -- | -- | -- | `OP.STR` | `CONFIRMED_LIVE` (established earlier this project, see `MOVIE_DETECTION.md`) |
| `MOVER.EXE` | -- | -- | -- | `GAI.STR` or `KIKU.STR` | `TABLE_ONLY` / `AMBIGUOUS` (see `MOVIE_DETECTION.md`) |

Table entries `MCAVE.EXE`, `MSB.EXE`, `MGOKI.EXE`: `UNUSED_CANDIDATE`
-- present in every chapter's name table, referenced by no file's real
name on disc, called by no found call site. Strong but not airtight
evidence of cut content (a file could theoretically exist under a
different name/location not yet checked, though none of this project's
disc-wide file cataloging to date has surfaced one).

## 9. Unknowns (explicit)

- Whether `CAP2.EXE`/`CAP3.EXE` trigger a movie at all, and if so, how
  (no call site to the known dispatcher was found; a different,
  unrelated function might exist that this scan didn't look for).
- Whether `CAPX.EXE`'s own `movie_id=9` call site ever actually fires
  live -- no save state currently available sits resident in
  `CAPX.EXE` to test it against.
- `MOVER.EXE`'s pairing to `GAI.STR` or `KIKU.STR` (unrelated to this
  investigation's scope, tracked separately in `MOVIE_DETECTION.md`).
- What the three "setup calls" after the print in the reconstructed
  pseudocode (§2) actually do -- out of this investigation's scope
  (movie *selection*, not the surrounding load machinery), left
  unexplored.
- Whether any chapter can select a movie via a genuinely dynamic
  (non-constant) value through some path this scanner's direct/
  indirect/data-table checks didn't cover -- `trace_register_backward`
  is a straight-line scan, not a full control-flow-graph analysis, so
  a value only resolvable by merging multiple branches would not be
  found by it.

## 10. Automation / code changes

- **`gcrts/mips_disasm.py`** (new): general MIPS-I instruction decoder
  covering every opcode this investigation's code needed to read real
  compiled function bodies (arithmetic/logical, loads/stores,
  branches, `lui`, `jr`/`jalr`; defers to the already-tested
  `gcrts.mips_jal_decoder` for `j`/`jal` target arithmetic specifically,
  rather than re-deriving it a third time in this project).
  10 tests, `tests/test_mips_disasm.py`.
- **`gcrts/movie_loader_scan.py`** (new): the reusable scanner --
  `find_movie_name_table`, `find_dispatcher`, `find_call_sites`,
  `trace_register_backward`, `scan_executable`/`scan_all`, and a CLI
  (`python -m gcrts.movie_loader_scan --out movie_loader_map.json`)
  emitting a machine-readable JSON database alongside a printed human
  summary. 7 tests, `tests/test_movie_loader_scan.py`, built entirely
  against small synthetic byte blobs (not the real disc image), so the
  suite runs anywhere -- validated separately against the real disc
  during this investigation (see §11).
- **`gcrts/movie_detection.py`**: `StaticMovieTrigger` gained a
  `confidence` field; `CAP0.EXE`'s entry is now `CONFIRMED_LIVE`. The
  module's own comments describing a `CAP0.EXE`→`CAPX.EXE` handoff
  were corrected to reflect §5-§7's findings. 2 new/changed tests.
- **`docs/renderer/MOVIE_DETECTION.md`** and
  **`docs/status/CURRENT_SYSTEM_STATUS.md`**: corrected the same wrong
  handoff claim.

A `movie_loader_map.json` database is regenerable at any time via
`python -m gcrts.movie_loader_scan --out movie_loader_map.json` against
the real disc image (`--disc` to override the path) -- not committed,
same precedent as this project's other bulk-regeneratable disc-derived
artifacts (`.gitignore`'s `audio_fingerprints.json` entry, etc.).

## 11. Evidence artifacts (reproducibility)

Every finding above can be reproduced with:

```
python -m gcrts.movie_loader_scan --out movie_loader_map.json
```

Key addresses, for direct cross-reference against the real disc image
(`קיבצי דמה/Twilight Syndrome - Tansaku Hen (Japan).bin`) or a live GDB
session:

- `CAP0.EXE` dispatcher entry: `0x8006E5E4` (file offset `0x29DE4`,
  `t_addr=0x80045000`). Format string ref: `0x8006E610`. Pointer table:
  `0x8009C514`. Call site: `0x8006CCB0` (`movie_id=8`).
- `CAPX.EXE` dispatcher entry: `0x80062018` (`t_addr=0x80035000`).
  Format string ref: `0x80062044`. Pointer table: `0x8008C04C`. Call
  site: `0x80041234` (`movie_id=9`). Live-tested: breakpoint armed here
  during a save-slot-6 `MPRO.EXE` load, never fired in 30s.
- Full per-file dispatcher/table/call-site addresses: see
  `movie_loader_map.json` (regenerate as above) or re-run
  `gcrts.movie_loader_scan.scan_all()` directly.

Live verification commands used this session (GDB remote protocol via
`scripts.gdb_cdinit_trigger_capture.BreakpointGdbClient`, port 3334):
armed an exec breakpoint (`Z0`) at the address in question, triggered
`state/load?slot=6` via the PCSX-Redux Web API, continued (`c`), and on
a stop-reply read `$a1` (GPR index 5 in the standard 32-GPR `g`-packet
layout) plus the pointer table's live bytes at its known address.
