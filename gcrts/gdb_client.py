"""Generic GDB remote-serial-protocol client -- no external deps, no
game-specific addresses.

Split out of `gcrts.live_extract` (which bundled this class together
with a hardcoded Twilight-Syndrome script-buffer address) per the
toolkit-readiness audit's finding that this was the clearest real
example of game-specific leakage into an otherwise-reusable module
(`docs/status/TOOLKIT_READINESS_AUDIT.md` §15). `gcrts.live_extract`
now imports `GdbClient` from here for backward compatibility; nothing
about its own public API changed.

Also consolidates the breakpoint/continue/register-read methods that
this project's own investigation scripts (`scripts/gdb_cdinit_trigger_capture.py`'s
`BreakpointGdbClient`, `scripts/live_movie_console_watch.py`) had
re-implemented as a subclass on top of the old bundled class -- those
scripts still work unmodified (their own subclass just now duplicates
methods already present on the base class, which is harmless), but any
new code should use this class directly rather than re-deriving the
same GDB remote-protocol arithmetic a third time.
"""
from __future__ import annotations

import socket
import time


def _checksum(data: bytes) -> str:
    return format(sum(data) & 0xFF, "02x")


def _is_console_output_packet(inner: str) -> bool:
    hex_part = inner[1:]
    return (
        inner.startswith("O")
        and len(hex_part) > 0
        and len(hex_part) % 2 == 0
        and all(c in "0123456789abcdefABCDEF" for c in hex_part)
    )


class GdbClient:
    """Minimal GDB remote-serial-protocol client."""

    def __init__(self, host: str = "127.0.0.1", port: int = 3334, timeout: float = 30.0):
        self._sock = socket.create_connection((host, port), timeout=timeout)
        self._sock.settimeout(timeout)

    def _send(self, packet: bytes) -> None:
        self._sock.sendall(b"$" + packet + b"#" + _checksum(packet).encode())

    def _read_packet(self) -> bytes:
        buf = b""
        while True:
            chunk = self._sock.recv(65536)
            if not chunk:
                break
            buf += chunk
            if b"#" in buf and len(buf) >= buf.index(b"#") + 3:
                break
        return buf

    def _read_reply(self) -> str:
        """Reads one reply packet, skipping any interleaved 'O' (hex-
        encoded console text) packets the target may send asynchronously
        while running -- these must never be mistaken for the actual
        reply to whatever was just sent (a real bug this project hit
        and fixed twice in earlier ad hoc scripts, now fixed once here).

        A real console packet is 'O' followed by a non-empty, even-length
        hex string -- checked precisely, not just a leading 'O', because
        the literal acknowledgment "OK" also starts with 'O' and must
        NOT be skipped: 'K' is not a valid hex digit, which is exactly
        what distinguishes the two."""
        while True:
            raw = self._read_packet()
            text = raw.decode(errors="replace")
            if "$" not in text or "#" not in text:
                return ""
            inner = text[text.index("$") + 1 : text.rindex("#")]
            if _is_console_output_packet(inner):
                continue
            return inner

    def read_memory(self, addr: int, length: int) -> bytes | None:
        self._send(f"m{addr:x},{length:x}".encode())
        inner = self._read_reply()
        if not inner or (inner.startswith("E") and len(inner) <= 3):
            return None
        return bytes.fromhex(inner)

    def write_memory(self, addr: int, data: bytes) -> bool:
        """Write bytes via the GDB remote protocol's 'M' packet
        (addr,length:hexdata). Returns True on an "OK" reply."""
        payload = f"M{addr:x},{len(data):x}:".encode() + data.hex().encode()
        self._send(payload)
        return self._read_reply() == "OK"

    def set_breakpoint(self, addr: int, length: int = 4) -> bool:
        self._send(f"Z0,{addr:x},{length:x}".encode())
        return self._read_reply() == "OK"

    def remove_breakpoint(self, addr: int, length: int = 4) -> bool:
        self._send(f"z0,{addr:x},{length:x}".encode())
        return self._read_reply() == "OK"

    def set_write_watchpoint(self, addr: int, length: int = 4) -> bool:
        self._send(f"Z2,{addr:x},{length:x}".encode())
        return self._read_reply() == "OK"

    def remove_write_watchpoint(self, addr: int, length: int = 4) -> bool:
        self._send(f"z2,{addr:x},{length:x}".encode())
        return self._read_reply() == "OK"

    def read_registers(self) -> bytes | None:
        self._send(b"g")
        inner = self._read_reply()
        if not inner or inner.startswith("E"):
            return None
        return bytes.fromhex(inner)

    def continue_and_wait_for_stop(self, timeout: float | None = None) -> str:
        """Send 'c' (continue) and block until a real stop-reply packet
        arrives. 'c' produces no reply of its own -- only the next stop
        does; treating it as anything else deadlocks (a real bug this
        project hit and documented in `gcrts.mips_jal_decoder`'s sibling
        investigation scripts)."""
        old_timeout = self._sock.gettimeout()
        if timeout is not None:
            self._sock.settimeout(timeout)
        try:
            self._send(b"c")
            deadline = None if timeout is None else time.monotonic() + timeout
            while True:
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return ""
                    self._sock.settimeout(remaining)
                try:
                    reply = self._read_reply()
                except (socket.timeout, TimeoutError):
                    return ""
                if reply:
                    return reply
        finally:
            self._sock.settimeout(old_timeout)

    def interrupt(self) -> None:
        """Send the raw GDB interrupt byte (0x03) to pause a freely-
        running target -- fire-and-forget, matching this project's own
        established pattern (see the statistical PC-sampling profiler
        in scripts/gdb_cdinit_trigger_capture.py)."""
        self._sock.sendall(b"\x03")

    def resume(self) -> None:
        """Send 'c' without waiting for any reply -- use when the
        caller doesn't need to block for the next stop."""
        self._send(b"c")

    def close(self) -> None:
        self._sock.close()
