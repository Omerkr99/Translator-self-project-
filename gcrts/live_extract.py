"""Live extraction of the current script buffer from a running PCSX-Redux
instance via its GDB remote stub, decoded with gcrts.script_decoder.

This is the "RAM (for validation)" half of Phase 1's extraction
requirement. The "Disk (true source via .CDB)" half is not yet
implemented -- the loader that fills 0x801fe800 hasn't been identified yet
(see NOTES.md's open threads).

`GdbClient` itself now lives in `gcrts.gdb_client` (a genuinely generic
GDB remote-protocol client, no game-specific addresses) -- re-exported
here for backward compatibility with existing callers
(`scripts/gdb_cdinit_trigger_capture.py` and others import it from this
module). See `docs/status/TOOLKIT_READINESS_AUDIT.md` §15 for why this
split happened.
"""
from __future__ import annotations

from gcrts.gdb_client import GdbClient
from gcrts.script_decoder import ScriptDocument, decode_script

SCRIPT_BUF_ADDR = 0x801FE800
DEFAULT_CAPTURE_WORDS = 2048  # generous upper bound; decode_script stops at 0xFFFF anyway


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
