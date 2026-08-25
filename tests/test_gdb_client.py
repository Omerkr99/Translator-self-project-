"""Tests for gcrts.gdb_client -- protocol framing only, via a fake
in-process socket, no real network/emulator dependency."""
from __future__ import annotations

from gcrts.gdb_client import GdbClient, _checksum


class _FakeSocket:
    """Stands in for a real TCP socket: records what was sent and plays
    back a queued sequence of raw GDB packet bytes on recv()."""

    def __init__(self, replies: list[bytes]):
        self._replies = list(replies)
        self.sent: list[bytes] = []
        self._timeout = None

    def sendall(self, data: bytes) -> None:
        self.sent.append(data)

    def recv(self, _n: int) -> bytes:
        if not self._replies:
            return b""
        return self._replies.pop(0)

    def settimeout(self, value) -> None:
        self._timeout = value

    def gettimeout(self):
        return self._timeout

    def close(self) -> None:
        pass


def _packet(inner: str) -> bytes:
    inner_b = inner.encode()
    return b"$" + inner_b + b"#" + _checksum(inner_b).encode()


def _make_client(replies: list[bytes]) -> GdbClient:
    client = GdbClient.__new__(GdbClient)
    client._sock = _FakeSocket(replies)
    return client


def test_read_memory_decodes_hex_reply():
    client = _make_client([_packet("deadbeef")])
    data = client.read_memory(0x80000000, 4)
    assert data == bytes.fromhex("deadbeef")


def test_read_memory_returns_none_on_error_reply():
    client = _make_client([_packet("E01")])
    assert client.read_memory(0x80000000, 4) is None


def test_write_memory_true_on_ok():
    client = _make_client([_packet("OK")])
    assert client.write_memory(0x80000000, b"\x01\x02") is True
    sent = client._sock.sent[0]
    assert sent.startswith(b"$M80000000,2:0102#")


def test_set_and_remove_breakpoint_send_z0_packets():
    client = _make_client([_packet("OK"), _packet("OK")])
    assert client.set_breakpoint(0x80010000) is True
    assert client.remove_breakpoint(0x80010000) is True
    assert client._sock.sent[0].startswith(b"$Z0,80010000,4#")
    assert client._sock.sent[1].startswith(b"$z0,80010000,4#")


def test_read_reply_skips_console_o_packets():
    """An asynchronous 'O' (console text) packet must never be mistaken
    for the actual reply to whatever was just sent."""
    client = _make_client([_packet("O48656c6c6f"), _packet("OK")])
    assert client.write_memory(0x80000000, b"\x00") is True


def test_continue_and_wait_for_stop_returns_stop_reply():
    client = _make_client([_packet("T05")])
    reply = client.continue_and_wait_for_stop(timeout=5.0)
    assert reply == "T05"
    assert client._sock.sent[0] == b"$c#63"


def test_read_registers_decodes_hex():
    client = _make_client([_packet("00" * 38)])
    regs = client.read_registers()
    assert regs == bytes(38)
