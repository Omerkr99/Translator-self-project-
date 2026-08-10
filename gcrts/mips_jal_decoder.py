"""Reusable MIPS J/JAL target and return-address decoder.

This project has hand-computed JAL targets and return addresses during
live investigation repeatedly, and gotten it wrong at least twice in
one session (see `EXPERIMENT_PLAN.md`): once treating a return address
as `pc+4` instead of the correct `pc+8` (the delay slot), and once
mis-computing a JAL target's shifted value by hand, silently testing a
completely unrelated function (`0x8003B1E4` instead of the real
`0x8003B224`) for an extended period before the mistake was caught.
Both were only caught by the SYMPTOM -- "this breakpoint never fires
despite confirmed activity" -- not by inspection, which is an
unreliable way to catch an arithmetic bug. This module makes the
arithmetic a single, tested function so it never needs to be
hand-derived again, and adds a validation helper that refuses to
proceed the moment live bytes disagree with what was expected, so a
stale address (this project's other repeated finding: code layout can
drift even within one continuously-running scene) is caught
immediately rather than producing a long, silent false negative.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

JAL_OPCODE = 0x03
J_OPCODE = 0x02


class InvalidJalInstructionError(ValueError):
    """Raised when the given instruction word's opcode isn't J/JAL."""


class CallSiteMismatchError(ValueError):
    """Raised by validate_call_site when live memory doesn't match what
    was expected -- signals a stale address / layout drift, not a logic
    bug in the caller."""


def opcode_of(instruction: int) -> int:
    """The 6-bit opcode field (bits 31-26) of a MIPS instruction word."""
    return (instruction >> 26) & 0x3F


@dataclass(frozen=True)
class JalDecodeResult:
    pc: int
    instruction: int
    opcode: int
    target: int
    return_address: int

    @property
    def is_jal(self) -> bool:
        return self.opcode == JAL_OPCODE

    @property
    def is_j(self) -> bool:
        return self.opcode == J_OPCODE


def decode_jal(pc: int, instruction: int, *, allow_j: bool = False) -> JalDecodeResult:
    """Decode a J/JAL instruction word located at address `pc`.

    ``target = ((pc + 4) & 0xF0000000) | ((instruction & 0x03FFFFFF) << 2)``
    ``return_address = pc + 8`` (the delay slot's own successor -- NOT
    `pc + 4`, a mistake this project made and had to re-catch this
    session).

    By default only JAL (opcode 0x03) is accepted -- J (opcode 0x02) has
    no meaningful return address, and this project's own investigations
    care about the call/return relationship, not just the jump target.
    Pass `allow_j=True` to also accept J, e.g. when decoding a tail-call
    or an unconditional local branch found while mapping a function body.

    Raises `InvalidJalInstructionError` rather than silently decoding an
    arbitrary word as if it were a jump -- this project's history shows
    that produces a plausible-looking but wrong address with no
    indication anything went wrong until a breakpoint mysteriously never
    fires.
    """
    opcode = opcode_of(instruction)
    valid_opcodes = {JAL_OPCODE, J_OPCODE} if allow_j else {JAL_OPCODE}
    if opcode not in valid_opcodes:
        expected = "/".join(f"{o:#04x}" for o in sorted(valid_opcodes))
        raise InvalidJalInstructionError(
            f"word {instruction:#010x} at pc={pc:#010x} has opcode {opcode:#04x}, expected {expected}"
        )
    target_field = instruction & 0x03FFFFFF
    target = ((pc + 4) & 0xF0000000) | (target_field << 2)
    return_address = pc + 8
    return JalDecodeResult(pc=pc, instruction=instruction, opcode=opcode, target=target, return_address=return_address)


def decode_jal_bytes(pc: int, raw: bytes, *, allow_j: bool = False) -> JalDecodeResult:
    """Same as `decode_jal`, but takes the 4 raw little-endian bytes a
    live memory read returns instead of a pre-parsed int."""
    if len(raw) != 4:
        raise ValueError(f"expected exactly 4 bytes, got {len(raw)}")
    return decode_jal(pc, int.from_bytes(raw, "little"), allow_j=allow_j)


@dataclass(frozen=True)
class CallSiteExpectation:
    """What a live capture SHOULD see if the address book this
    expectation was built from is still valid for whatever is currently
    loaded. `profile_name` is purely informational (surfaced in any
    error raised), matching `gcrts.mips_patch_profile`'s own convention
    of naming which executable/profile a set of addresses belongs to."""

    call_site_addr: int
    expected_instruction: int
    expected_target: int
    expected_return_address: int
    profile_name: str | None = None


def validate_call_site(
    expectation: CallSiteExpectation,
    read_memory: Callable[[int, int], "bytes | None"],
) -> JalDecodeResult:
    """Read the live 4 bytes at `expectation.call_site_addr`, decode
    them, and check every computed value against what was expected.

    Raises `CallSiteMismatchError` -- never silently returns a
    best-effort result -- the moment any of these disagree, checked in
    order from "stalest possible signal" to most specific:

    1. The read itself failed (address unmapped / connection issue).
    2. The raw instruction word doesn't match what was expected -- the
       whole address book may have shifted, or this may not even be a
       JAL any more.
    3. The decoded target doesn't match.
    4. The decoded return address doesn't match.

    `read_memory` is injected (matching `gcrts.mips_patch_profile.
    identify_loaded_executable`'s own convention) so this stays testable
    without a live emulator connection.
    """
    raw = read_memory(expectation.call_site_addr, 4)
    if raw is None or len(raw) != 4:
        raise CallSiteMismatchError(
            f"could not read 4 bytes at {expectation.call_site_addr:#010x} "
            f"(profile={expectation.profile_name!r})"
        )
    live_instruction = int.from_bytes(raw, "little")
    if live_instruction != expectation.expected_instruction:
        raise CallSiteMismatchError(
            f"call site {expectation.call_site_addr:#010x} holds {live_instruction:#010x}, "
            f"expected {expectation.expected_instruction:#010x} "
            f"(profile={expectation.profile_name!r}) -- code layout likely drifted"
        )

    decoded = decode_jal(expectation.call_site_addr, live_instruction)
    if decoded.target != expectation.expected_target:
        raise CallSiteMismatchError(
            f"call site {expectation.call_site_addr:#010x} decodes to target "
            f"{decoded.target:#010x}, expected {expectation.expected_target:#010x} "
            f"(profile={expectation.profile_name!r})"
        )
    if decoded.return_address != expectation.expected_return_address:
        raise CallSiteMismatchError(
            f"call site {expectation.call_site_addr:#010x} decodes to return address "
            f"{decoded.return_address:#010x}, expected {expectation.expected_return_address:#010x} "
            f"(profile={expectation.profile_name!r})"
        )
    return decoded
