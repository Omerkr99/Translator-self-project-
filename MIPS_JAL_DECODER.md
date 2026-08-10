# MIPS JAL Decoder — Reusable Tooling

Implemented in `gcrts.mips_jal_decoder`, tested in
`tests/test_mips_jal_decoder.py` (15 tests, all passing; 294 total
project-wide). Built specifically because this project's own live
investigation hand-computed JAL targets and return addresses
repeatedly, and got it wrong twice in one session before this tool
existed — both times the mistake was only caught by the symptom ("this
breakpoint never fires despite confirmed activity"), not by
inspection, which is an unreliable way to catch an arithmetic bug.

## What it replaces

Before this tool, every live investigation script in this session's
scratchpad computed JAL targets by hand:

```python
target_field = (word & 0x03FFFFFF)
target = (target_field << 2) | 0x80000000   # WRONG in general -- see below
return_address = jal_pc + 4                  # WRONG -- off by one instruction
```

Two concrete failures this session:

1. **Return address off-by-one-instruction**: assumed `jal_pc + 4`
   (the delay slot's own address) instead of `jal_pc + 8` (the delay
   slot's successor — where execution actually resumes after the
   call). Caused an entry-point breakpoint filter to show "0 hits from
   the expected caller" for an entire capture round before the
   arithmetic was corrected.
2. **Hand-computed target arithmetic slip**: decoding the JAL word at
   `0x8003a90c` (`0x0c00ec89`) by hand produced `0x8003B1E4` — plausible
   enough to look like a real function address, and even reachable via
   *other*, unrelated callers, which made the mistake far harder to
   notice than an outright crash. The correct target is `0x8003B224`.
   An entire round of breakpoint attempts against the wrong address
   produced consistent, confusing "zero matching hits" results before
   this was caught.

## The functions

```python
from gcrts.mips_jal_decoder import decode_jal, decode_jal_bytes, validate_call_site, CallSiteExpectation

result = decode_jal(pc=0x8003a90c, instruction=0x0c00ec89)
result.target           # 0x8003b224
result.return_address   # 0x8003a914  (pc + 8, not pc + 4)
result.is_jal           # True
```

`decode_jal_bytes(pc, raw_4_bytes)` — same thing, takes the raw bytes a
live GDB memory read returns directly.

Both raise `InvalidJalInstructionError` if the given word's opcode
isn't J/JAL (opcode `0x02`/`0x03`) — refusing to silently decode an
arbitrary instruction as if it were a jump, rather than producing a
plausible-looking wrong answer.

```python
expectation = CallSiteExpectation(
    call_site_addr=0x8003a90c,
    expected_instruction=0x0c00ec89,
    expected_target=0x8003b224,
    expected_return_address=0x8003a914,
    profile_name="chapter1",
)
result = validate_call_site(expectation, read_memory)  # read_memory: (addr, len) -> bytes|None
```

`validate_call_site` reads the live 4 bytes at the call site and
raises `CallSiteMismatchError` — never silently proceeds — the moment
any of these disagree, checked from least to most specific:

1. The read itself failed.
2. The live instruction word doesn't match what was expected — the
   whole address book may have shifted (this project's own repeatedly-
   confirmed "code layout can drift mid-scene, not just across
   quickloads" finding).
3. The decoded target doesn't match.
4. The decoded return address doesn't match.

`read_memory` is dependency-injected (matching
`gcrts.mips_patch_profile.identify_loaded_executable`'s own
convention), so this is fully unit-testable without a live emulator —
see the test file for fake-reader-based coverage of every failure mode.

## Usage discipline going forward

Any future live investigation script that computes a JAL target or a
return address by hand instead of calling `decode_jal`/
`decode_jal_bytes` is reintroducing exactly the bug class this module
exists to close. Any script that arms a breakpoint against an address
derived from an earlier session/profile without first calling
`validate_call_site` (or an equivalent live re-check) is reintroducing
the "stale address" bug class this project has hit repeatedly. Neither
should happen again without a specific reason documented inline.
