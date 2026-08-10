"""Live extraction of the current script buffer from a running PCSX-Redux
instance via its GDB remote stub, decoded with gcrts.script_decoder.

This is the "RAM (for validation)" half of Phase 1's extraction
requirement. The "Disk (true source via .CDB)" half is not yet
implemented -- the loader that fills 0x801fe800 hasn't been identified yet
(see NOTES.md's open threads).
"""
from __future__ import annotations

import socket
import struct

from gcrts.script_decoder import ScriptDocument, decode_script

SCRIPT_BUF_ADDR = 0x801FE800
DEFAULT_CAPTURE_WORDS = 2048  # generous upper bound; decode_script stops at 0xFFFF anyway


def _checksum(data: bytes) -> str:
    return format(sum(data) & 0xFF, "02x")


class GdbClient:
    """Minimal GDB remote-serial-protocol client (no external deps)."""

    def __init__(self, host: str = "127.0.0.1", port: int = 3333, timeout: float = 30.0):
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

    def read_memory(self, addr: int, length: int) -> bytes | None:
        self._send(f"m{addr:x},{length:x}".encode())
        raw = self._read_packet()
        text = raw.decode(errors="replace")
        if "$" not in text or "#" not in text:
            return None
        inner = text[text.index("$") + 1 : text.rindex("#")]
        if inner.startswith("E") and len(inner) <= 3:
            return None
        return bytes.fromhex(inner)

    def write_memory(self, addr: int, data: bytes) -> bool:
        """Write bytes via the GDB remote protocol's 'M' packet
        (addr,length:hexdata). Returns True on an "OK" reply."""
        payload = f"M{addr:x},{len(data):x}:".encode() + data.hex().encode()
        self._send(payload)
        raw = self._read_packet()
        text = raw.decode(errors="replace")
        if "$" not in text or "#" not in text:
            return False
        inner = text[text.index("$") + 1 : text.rindex("#")]
        return inner == "OK"

    def close(self) -> None:
        self._sock.close()


def capture_script_buffer(
    host: str = "127.0.0.1", port: int = 3333, n_words: int = DEFAULT_CAPTURE_WORDS
) -> bytes:
    """Dump `n_words` 16-bit words starting at the script buffer address
    from a live, running game."""
    client = GdbClient(host, port)
    try:
        CHUNK = 0x1000
        length = n_words * 2
        out = bytearray()
        addr = SCRIPT_BUF_ADDR
        end = SCRIPT_BUF_ADDR + length
        while addr < end:
            n = min(CHUNK, end - addr)
            data = client.read_memory(addr, n)
            if data is None:
                data = b"\x00" * n
            out += data
            addr += n
        return bytes(out)
    finally:
        client.close()


def extract_and_decode(
    host: str = "127.0.0.1", port: int = 3333, n_words: int = DEFAULT_CAPTURE_WORDS
) -> tuple[bytes, ScriptDocument]:
    raw = capture_script_buffer(host, port, n_words)
    doc = decode_script(raw)
    return raw, doc


def write_script_buffer(
    encoded: bytes, host: str = "127.0.0.1", port: int = 3333
) -> bool:
    """Write a re-encoded script buffer (gcrts.script_encoder.encode_script
    output -- must already end with the 0xFFFF terminator) back over the
    live script buffer in RAM. Only the given bytes are touched; nothing
    beyond `len(encoded)` is written, so anything past the terminator that
    wasn't part of the original capture is left alone."""
    client = GdbClient(host, port)
    try:
        CHUNK = 0x400
        for offset in range(0, len(encoded), CHUNK):
            chunk = encoded[offset : offset + CHUNK]
            if not client.write_memory(SCRIPT_BUF_ADDR + offset, chunk):
                return False
        return True
    finally:
        client.close()


if __name__ == "__main__":
    import json
    import sys

    raw, doc = extract_and_decode()
    print(f"captured {len(raw)} bytes, decoded {len(doc.codes)} codes", file=sys.stderr)
    print(json.dumps(doc.to_dict(), indent=2))
