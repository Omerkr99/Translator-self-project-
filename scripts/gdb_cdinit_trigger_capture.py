"""One-shot precision RAM capture triggered by a real GDB hardware
breakpoint, instead of PCSX-Redux's in-process Lua `addBreakpoint`
mechanism (which failed to fire twice in a row this session despite a
byte-verified-correct target address -- see docs/audio/AUDIO_DATA_TRACE.md).
GDB-based breakpoints have an actual track record in this project
(the original CD_init/SPUCNT correlation captures in
docs/audio/SPU_AUDIO_PATH_DISCOVERY.md), unlike the Lua tracer, which is
the same mechanism that caused the whole control-flow-tracing pivot.

Reuses gcrts.live_extract.GdbClient's read_memory (already proven
working in this codebase) and adds breakpoint set/continue/wait-for-stop
on top -- the minimum GDB remote-protocol surface needed for a one-shot
"stop exactly here, dump RAM, resume" capture.

Usage:
    python -m scripts.gdb_cdinit_trigger_capture --addr 0x80081BB8 --out cdinit_trigger.bin
"""
from __future__ import annotations

import argparse
import socket
import sys

from gcrts.live_extract import GdbClient

RAM_SIZE = 0x200000
RAM_BASE = 0x80000000


def _checksum(data: bytes) -> str:
    return format(sum(data) & 0xFF, "02x")


class BreakpointGdbClient(GdbClient):
    def set_breakpoint(self, addr: int) -> bool:
        self._send(f"Z0,{addr:x},4".encode())
        reply = self._read_reply()
        return reply == "OK"

    def remove_breakpoint(self, addr: int) -> bool:
        self._send(f"z0,{addr:x},4".encode())
        reply = self._read_reply()
        return reply == "OK"

    def set_write_watchpoint(self, addr: int, length: int = 4) -> bool:
        """GDB remote protocol 'Z2' = write watchpoint."""
        self._send(f"Z2,{addr:x},{length:x}".encode())
        reply = self._read_reply()
        return reply == "OK"

    def remove_write_watchpoint(self, addr: int, length: int = 4) -> bool:
        self._send(f"z2,{addr:x},{length:x}".encode())
        reply = self._read_reply()
        return reply == "OK"

    def read_registers(self) -> bytes | None:
        self._send(b"g")
        # Skip any interleaved 'O' (console text) packets -- the same
        # class of bug found and fixed in continue_and_wait_for_stop.
        while True:
            raw = self._read_packet()
            text = raw.decode(errors="replace")
            if "$" not in text or "#" not in text:
                return None
            inner = text[text.index("$") + 1 : text.rindex("#")]
            if inner.startswith("O"):
                continue
            if inner.startswith("E"):
                return None
            return bytes.fromhex(inner)

    def continue_and_wait_for_stop(self, timeout: float) -> str:
        """Send 'c' (continue) and block until a real stop-reply packet
        arrives (a breakpoint hit or other signal, starting with 'T' or
        'S'). PCSX-Redux's stub also sends 'O' packets asynchronously
        while the target keeps running -- hex-encoded console text
        (e.g. the game's own "CD_init:addr=..." debug print) -- which
        must be skipped, not mistaken for a stop."""
        import time

        old_timeout = self._sock.gettimeout()
        deadline = time.monotonic() + timeout
        self._sock.settimeout(timeout)
        try:
            self._send(b"c")
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return ""
                self._sock.settimeout(remaining)
                try:
                    reply = self._read_reply()
                except (socket.timeout, TimeoutError):
                    return ""
                if not reply:
                    return ""
                if reply.startswith("O"):
                    try:
                        text = bytes.fromhex(reply[1:]).decode(errors="replace")
                    except ValueError:
                        text = reply[1:]
                    print(f"[console] {text.rstrip()}", file=sys.stderr)
                    continue
                return reply
        finally:
            self._sock.settimeout(old_timeout)

    def _read_reply(self) -> str:
        raw = self._read_packet()
        text = raw.decode(errors="replace")
        if "$" not in text or "#" not in text:
            return ""
        return text[text.index("$") + 1 : text.rindex("#")]

    def read_full_ram(self) -> bytes:
        CHUNK = 0x1000
        out = bytearray()
        addr = RAM_BASE
        end = RAM_BASE + RAM_SIZE
        while addr < end:
            n = min(CHUNK, end - addr)
            data = self.read_memory(addr, n)
            if data is None:
                data = b"\x00" * n
            out += data
            addr += n
        return bytes(out)


def capture_on_breakpoint(
    addr: int, out_path: str, host: str = "127.0.0.1", port: int = 3334, timeout: float = 300.0
) -> bool:
    client = BreakpointGdbClient(host, port)
    try:
        print(f"connected to GDB stub at {host}:{port}", file=sys.stderr)
        if not client.set_breakpoint(addr):
            print(f"FAILED to set breakpoint at 0x{addr:08X}", file=sys.stderr)
            return False
        print(f"breakpoint armed at 0x{addr:08X}; waiting up to {timeout:.0f}s for it to fire...", file=sys.stderr)
        reply = client.continue_and_wait_for_stop(timeout)
        if not reply:
            print("no stop-reply received (timeout or connection issue)", file=sys.stderr)
            return False
        print(f"stop-reply: {reply}", file=sys.stderr)
        ram = client.read_full_ram()
        with open(out_path, "wb") as f:
            f.write(ram)
        print(f"wrote {len(ram)} bytes to {out_path}", file=sys.stderr)
        client.remove_breakpoint(addr)
        return True
    finally:
        client.close()


def capture_on_write_watchpoint(
    addr: int, length: int, out_path: str, host: str = "127.0.0.1", port: int = 3334, timeout: float = 300.0
) -> bool:
    client = BreakpointGdbClient(host, port)
    try:
        print(f"connected to GDB stub at {host}:{port}", file=sys.stderr)
        if not client.set_write_watchpoint(addr, length):
            print(f"FAILED to set write watchpoint at 0x{addr:08X} (len {length})", file=sys.stderr)
            return False
        print(f"write watchpoint armed at 0x{addr:08X} (len {length}); waiting up to {timeout:.0f}s...", file=sys.stderr)
        reply = client.continue_and_wait_for_stop(timeout)
        if not reply:
            print("no stop-reply received (timeout or connection issue)", file=sys.stderr)
            return False
        print(f"stop-reply: {reply}", file=sys.stderr)
        regs = client.read_registers()
        if regs is not None:
            print(f"raw register bytes ({len(regs)}): {regs.hex()}", file=sys.stderr)
            # Standard MIPS 'g' packet layout: 32 GPRs (4 bytes each),
            # then status/lo/hi/badvaddr/cause/pc (4 bytes each).
            # pc is typically the 6th register after the 32 GPRs.
            if len(regs) >= (32 + 6) * 4:
                import struct as _struct
                pc = _struct.unpack_from("<I", regs, (32 + 5) * 4)[0]
                print(f"parsed PC (best-effort, standard MIPS layout): 0x{pc:08X}", file=sys.stderr)
        ram = client.read_full_ram()
        with open(out_path, "wb") as f:
            f.write(ram)
        print(f"wrote {len(ram)} bytes to {out_path}", file=sys.stderr)
        client.remove_write_watchpoint(addr, length)
        return True
    finally:
        client.close()


def log_watchpoint_sequence(
    addr: int,
    length: int,
    out_path: str,
    host: str = "127.0.0.1",
    port: int = 3334,
    total_timeout: float = 180.0,
) -> bool:
    """Arm a write watchpoint and keep continuing after every hit,
    logging a lightweight (address contents only, not a full 2MB dump)
    timestamped record each time -- builds a timeline of every write to
    this address across a real play session, so it can be correlated
    against a human narrating exactly when the target line is heard."""
    import json
    import time

    client = BreakpointGdbClient(host, port)
    events: list[dict] = []
    t0 = time.monotonic()
    try:
        print(f"connected to GDB stub at {host}:{port}", file=sys.stderr)
        if not client.set_write_watchpoint(addr, length):
            print(f"FAILED to set write watchpoint at 0x{addr:08X}", file=sys.stderr)
            return False
        print(f"write watchpoint armed at 0x{addr:08X} (len {length}); logging for up to {total_timeout:.0f}s...", file=sys.stderr)
        deadline = t0 + total_timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                print("total timeout reached", file=sys.stderr)
                break
            reply = client.continue_and_wait_for_stop(remaining)
            if not reply:
                print("no more stops (timeout)", file=sys.stderr)
                break
            t = time.monotonic() - t0
            data = client.read_memory(addr, length)
            values = []
            if data is not None:
                import struct as _struct
                for i in range(0, len(data) - 3, 4):
                    values.append(_struct.unpack_from("<I", data, i)[0])
            event = {"t": round(t, 2), "reply": reply, "values": values}
            events.append(event)
            print(f"[t={t:6.2f}s] fired -- values={values}", file=sys.stderr)
        with open(out_path, "w") as f:
            json.dump(events, f, indent=2)
        print(f"wrote {len(events)} event(s) to {out_path}", file=sys.stderr)
        client.remove_write_watchpoint(addr, length)
        return True
    finally:
        client.close()


# Already-known CD-ROM command-issuing call sites (gcrts.cdrom_setfilter /
# gcrts.cdrom_driver_map, reused verbatim -- see pcsx_lua/spu_playback_trace.lua's
# own CD_COMMAND_SITES). At each, $v0 holds the command byte about to be
# written to the real hardware command register. Per docs/audio/AUDIO_PLAYBACK_TRUTH.md,
# the one command that actually plays XA-ADPCM (ReadS, 0x1B) has never been
# observed at any of these sites in any capture this project has taken.
CD_COMMAND_SITES = [0x8008182C, 0x80081AC8, 0x80081C2C, 0x80081C00]
READS_COMMAND = 0x1B

# Standard MIPS 'g'-packet register layout, confirmed this session by
# cross-checking a captured $a0 against the disassembled SW instruction's
# own base register: 32 GPRs (r0=zero .. r31), then status/lo/hi/badvaddr/cause/pc.
REG_V0_INDEX = 2
REG_PC_INDEX = 32 + 5


def _parse_reg(regs: bytes, index: int) -> int:
    import struct as _struct

    return _struct.unpack_from("<I", regs, index * 4)[0]


def log_command_sequence(
    sites: list[int],
    out_path: str,
    host: str = "127.0.0.1",
    port: int = 3334,
    total_timeout: float = 180.0,
) -> bool:
    """Arm exec breakpoints on every known CD-ROM command-issuing call
    site simultaneously, and log (timestamp, site, command byte) for
    every hit over an extended window -- specifically to check whether
    ReadS (0x1B) is ever issued, and if so, exactly when relative to a
    human narrating the target dialogue line."""
    import json
    import time

    client = BreakpointGdbClient(host, port)
    events: list[dict] = []
    t0 = time.monotonic()
    try:
        print(f"connected to GDB stub at {host}:{port}", file=sys.stderr)
        for addr in sites:
            if not client.set_breakpoint(addr):
                print(f"FAILED to arm breakpoint at 0x{addr:08X}", file=sys.stderr)
                return False
        print(f"armed {len(sites)} CD command site(s); logging for up to {total_timeout:.0f}s...", file=sys.stderr)
        deadline = t0 + total_timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                print("total timeout reached", file=sys.stderr)
                break
            reply = client.continue_and_wait_for_stop(remaining)
            if not reply:
                print("no more stops (timeout)", file=sys.stderr)
                break
            t = time.monotonic() - t0
            regs = client.read_registers()
            if regs is None or len(regs) < (REG_PC_INDEX + 1) * 4:
                print(f"[t={t:6.2f}s] fired but could not read registers", file=sys.stderr)
                continue
            pc = _parse_reg(regs, REG_PC_INDEX)
            v0 = _parse_reg(regs, REG_V0_INDEX)
            cmd_byte = v0 & 0xFF
            flag = " <-- READS (XA-ADPCM PLAYBACK!)" if cmd_byte == READS_COMMAND else ""
            event = {"t": round(t, 2), "pc": hex(pc), "v0": hex(v0), "command_byte": hex(cmd_byte)}
            events.append(event)
            print(f"[t={t:6.2f}s] pc=0x{pc:08X} v0=0x{v0:08X} command_byte=0x{cmd_byte:02X}{flag}", file=sys.stderr)
        with open(out_path, "w") as f:
            json.dump(events, f, indent=2)
        print(f"wrote {len(events)} event(s) to {out_path}", file=sys.stderr)
        for addr in sites:
            client.remove_breakpoint(addr)
        return True
    finally:
        client.close()


def _read_reply_skip_console(client: "BreakpointGdbClient", timeout: float = 5.0) -> str:
    """Reads GDB reply packets, discarding any 'O' (hex-encoded console
    text) packets PCSX-Redux may interleave asynchronously, until a
    real reply (or a timeout) is found. Same class of bug as the one
    fixed in continue_and_wait_for_stop -- an 'O' packet must never be
    mistaken for the actual reply to whatever was just sent."""
    import time as _time

    deadline = _time.monotonic() + timeout
    while True:
        remaining = deadline - _time.monotonic()
        if remaining <= 0:
            return ""
        client._sock.settimeout(remaining)
        reply = client._read_reply()
        if not reply:
            return ""
        if reply.startswith("O"):
            continue
        return reply


SPU_TRANSFER_ADDR = 0x1F801DA6
SPU_DATA_FIFO = 0x1F801DA8


def log_spu_mmio_watchpoints(
    out_path: str,
    host: str = "127.0.0.1",
    port: int = 3334,
    total_timeout: float = 180.0,
) -> bool:
    """Arm write watchpoints on the SPU's real hardware Sound RAM Data
    Transfer Address (0x1F801DA6) and Data FIFO (0x1F801DA8) registers --
    NOT a memory peek (already confirmed stuck-zero in
    docs/audio/AUDIO_TRANSPORT_PATH.md), but a genuine write-instruction
    trap, which is a different underlying mechanism and may not share
    that limitation. Logs every hit with the writer's PC and the value
    written (read from CPU registers, not from the MMIO address itself)."""
    import json
    import time

    client = BreakpointGdbClient(host, port)
    events: list[dict] = []
    t0 = time.monotonic()
    try:
        print(f"connected to GDB stub at {host}:{port}", file=sys.stderr)
        if not client.set_write_watchpoint(SPU_TRANSFER_ADDR, 2):
            print("FAILED to arm watchpoint on Transfer Address", file=sys.stderr)
            return False
        if not client.set_write_watchpoint(SPU_DATA_FIFO, 2):
            print("FAILED to arm watchpoint on Data FIFO", file=sys.stderr)
            return False
        print(f"armed both SPU MMIO watchpoints; logging for up to {total_timeout:.0f}s...", file=sys.stderr)
        deadline = t0 + total_timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                print("total timeout reached", file=sys.stderr)
                break
            reply = client.continue_and_wait_for_stop(remaining)
            if not reply:
                print("no more stops (timeout)", file=sys.stderr)
                break
            t = time.monotonic() - t0
            regs = client.read_registers()
            pc = v0 = a0 = a1 = None
            if regs is not None and len(regs) >= (REG_PC_INDEX + 1) * 4:
                pc = _parse_reg(regs, REG_PC_INDEX)
                v0 = _parse_reg(regs, REG_V0_INDEX)
                a0 = _parse_reg(regs, 4)
                a1 = _parse_reg(regs, 5)
            event = {"t": round(t, 2), "pc": hex(pc) if pc else None, "v0": hex(v0) if v0 else None,
                     "a0": hex(a0) if a0 else None, "a1": hex(a1) if a1 else None}
            events.append(event)
            print(f"[t={t:6.2f}s] pc={event['pc']} v0={event['v0']} a0={event['a0']} a1={event['a1']}", file=sys.stderr)
        with open(out_path, "w") as f:
            json.dump(events, f, indent=2)
        print(f"wrote {len(events)} event(s) to {out_path}", file=sys.stderr)
        client.remove_write_watchpoint(SPU_TRANSFER_ADDR, 2)
        client.remove_write_watchpoint(SPU_DATA_FIFO, 2)
        return True
    finally:
        client.close()


# The two Transfer-Address write sites and the one Data-FIFO write site
# found this session via a coarse SPU-MMIO-block watchpoint, then
# individually disassembled and confirmed by their exact immediate
# offset (+0x1A6 = Transfer Address, +0x1A8 = Data FIFO; +0x1AA =
# SPUCNT, a false-positive from the watchpoint's coarser granularity,
# excluded here).
SPU_TRANSFER_ADDR_SITES = {0x8008EE60: "TRANSFER_ADDR", 0x8008F2CC: "TRANSFER_ADDR"}
SPU_FIFO_SITES = {0x8008EEF8: "FIFO"}


def log_spu_upload_events(
    out_path: str,
    host: str = "127.0.0.1",
    port: int = 3334,
    total_timeout: float = 240.0,
) -> bool:
    """Disciplined SPU Sound RAM upload logger. Arms real exec
    breakpoints on the exact, individually-disassembled Transfer
    Address / Data FIFO write sites (not a coarse MMIO watchpoint,
    which was shown this session to also fire on unrelated SPUCNT
    writes at +0x1AA). Every event is a genuine executed store --
    GDB only reports a stop after the target actually runs and hits
    the breakpoint, so consecutive events cannot be the same paused
    instruction reported twice; each carries its own fresh register
    read. For every event, records: timestamp, writer PC, event type,
    written value, the running current Transfer Address (real SPU RAM
    byte offset = value * 8, per PS1 hardware), the live-identified
    overlay (gcrts.overlay_identity, real signature match, never
    guessed), and the current LBA-tracking pair at 0xA60F0 (cheap,
    already-verified-real from earlier this session) for context."""
    import json
    import time

    sys.path.insert(0, ".")
    from gcrts import overlay_identity

    all_sites = {**SPU_TRANSFER_ADDR_SITES, **SPU_FIFO_SITES}
    client = BreakpointGdbClient(host, port)
    events: list[dict] = []
    t0 = time.monotonic()
    current_transfer_addr = None
    try:
        print(f"connected to GDB stub at {host}:{port}", file=sys.stderr)
        for addr in all_sites:
            if not client.set_breakpoint(addr):
                print(f"FAILED to arm breakpoint at 0x{addr:08X}", file=sys.stderr)
                return False
        print(f"armed {len(all_sites)} exact SPU upload site(s); logging for up to {total_timeout:.0f}s...", file=sys.stderr)
        deadline = t0 + total_timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                print("total timeout reached", file=sys.stderr)
                break
            reply = client.continue_and_wait_for_stop(remaining)
            if not reply:
                print("no more stops (timeout)", file=sys.stderr)
                break
            t = time.monotonic() - t0
            regs = client.read_registers()
            if regs is None or len(regs) < (REG_PC_INDEX + 1) * 4:
                print(f"[t={t:6.2f}s] fired but could not read registers -- SKIPPED (not counted as a valid event)", file=sys.stderr)
                continue
            pc = _parse_reg(regs, REG_PC_INDEX)
            v0 = _parse_reg(regs, REG_V0_INDEX)
            event_type = all_sites.get(pc, "UNKNOWN_SITE")
            written = v0 & 0xFFFF
            if event_type == "TRANSFER_ADDR":
                current_transfer_addr = written * 8

            overlay = overlay_identity.identify_overlay(lambda a, n: client.read_memory(a, n))
            overlay_name = overlay.name if overlay else "UNKNOWN"

            lba_data = client.read_memory(0xA60F0, 8)
            lba_pair = None
            if lba_data is not None:
                import struct as _struct
                lba_pair = list(_struct.unpack("<II", lba_data))

            event = {
                "t": round(t, 2),
                "pc": hex(pc),
                "type": event_type,
                "value": hex(written),
                "current_transfer_addr_spu_offset": hex(current_transfer_addr) if current_transfer_addr is not None else None,
                "overlay": overlay_name,
                "lba_context": lba_pair,
            }
            events.append(event)
            print(
                f"[t={t:7.2f}s] {event_type:14s} pc=0x{pc:08X} value=0x{written:04X} "
                f"transfer_addr_spu_offset={event['current_transfer_addr_spu_offset']} "
                f"overlay={overlay_name} lba_context={lba_pair}",
                file=sys.stderr,
            )
        with open(out_path, "w") as f:
            json.dump(events, f, indent=2)
        print(f"wrote {len(events)} event(s) to {out_path}", file=sys.stderr)
        for addr in all_sites:
            client.remove_breakpoint(addr)
        return True
    finally:
        client.close()


# Real PS1 hardware CD-ROM Data FIFO -- per psx-spx, and confirmed
# against this project's own earlier register table
# (docs/audio/XA_STREAM_RESOLUTION.md: 0x1F801802 = Parameter FIFO / Data).
# Reading this register (regardless of the CD-ROM's internal index bits)
# returns the next byte of whatever sector is currently being
# transferred out to the CPU -- this is the guest-visible mechanism a
# game must use to pull sector bytes when no system DMA channel is
# active (already confirmed true for this game -- zero DMA3/DMA4
# activity found in an earlier milestone).
CD_DATA_FIFO = 0x1F801802


class ReadWatchpointGdbClient(BreakpointGdbClient):
    def set_read_watchpoint(self, addr: int, length: int = 1) -> bool:
        self._send(f"Z3,{addr:x},{length:x}".encode())
        return self._read_reply() == "OK"

    def remove_read_watchpoint(self, addr: int, length: int = 1) -> bool:
        self._send(f"z3,{addr:x},{length:x}".encode())
        return self._read_reply() == "OK"


def log_cd_data_stream(
    out_path: str,
    host: str = "127.0.0.1",
    port: int = 3334,
    total_timeout: float = 120.0,
) -> bool:
    """Reconstruct the actual CD-ROM sector byte stream the game reads,
    by watching real reads of the Data FIFO register (0x1F801802) --
    the guest-visible mechanism for pulling sector bytes without system
    DMA, per this project's own earlier finding that DMA3/DMA4 are
    inactive. Also watches the already-known CD command-issuing sites
    so each FIFO byte can be correlated against the most recent
    Setloc/ReadN command in the same timeline. Every event is one real
    executed instruction (exec breakpoints for commands, a genuine
    read-trap for the FIFO), never a repeated stale state."""
    import json
    import time

    client = ReadWatchpointGdbClient(host, port)
    events: list[dict] = []
    fifo_position = 0
    t0 = time.monotonic()
    try:
        print(f"connected to GDB stub at {host}:{port}", file=sys.stderr)
        if not client.set_read_watchpoint(CD_DATA_FIFO, 1):
            print("FAILED to arm CD Data FIFO read watchpoint", file=sys.stderr)
            return False
        for addr in CD_COMMAND_SITES:
            if not client.set_breakpoint(addr):
                print(f"FAILED to arm command site 0x{addr:08X}", file=sys.stderr)
                return False
        print(f"armed CD Data FIFO read watchpoint + {len(CD_COMMAND_SITES)} command sites; logging for up to {total_timeout:.0f}s...", file=sys.stderr)
        deadline = t0 + total_timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                print("total timeout reached", file=sys.stderr)
                break
            reply = client.continue_and_wait_for_stop(remaining)
            if not reply:
                print("no more stops (timeout)", file=sys.stderr)
                break
            t = time.monotonic() - t0
            regs = client.read_registers()
            if regs is None or len(regs) < (REG_PC_INDEX + 1) * 4:
                continue
            pc = _parse_reg(regs, REG_PC_INDEX)
            if pc in CD_COMMAND_SITES:
                v0 = _parse_reg(regs, REG_V0_INDEX)
                event = {"t": round(t, 3), "type": "COMMAND", "pc": hex(pc), "command_byte": hex(v0 & 0xFF)}
            else:
                data = client.read_memory(CD_DATA_FIFO, 1)
                byte_val = data[0] if data else None
                event = {"t": round(t, 3), "type": "FIFO_BYTE", "pc": hex(pc), "position": fifo_position, "value": byte_val}
                fifo_position += 1
            events.append(event)
        with open(out_path, "w") as f:
            json.dump(events, f, indent=2)
        n_fifo = sum(1 for e in events if e["type"] == "FIFO_BYTE")
        n_cmd = sum(1 for e in events if e["type"] == "COMMAND")
        print(f"wrote {len(events)} event(s) ({n_fifo} FIFO bytes, {n_cmd} commands) to {out_path}", file=sys.stderr)
        client.remove_read_watchpoint(CD_DATA_FIFO, 1)
        for addr in CD_COMMAND_SITES:
            client.remove_breakpoint(addr)
        return True
    finally:
        client.close()


def log_execution_hit_counters(
    targets: list[int],
    out_path: str,
    host: str = "127.0.0.1",
    port: int = 3334,
    total_timeout: float = 150.0,
) -> bool:
    """Lightweight hit-counter only -- no register reads beyond the
    minimum needed to identify which of `targets` fired, no data
    capture. Records just (timestamp, target_pc) per hit so that
    before/during/after buckets can be reconstructed offline against
    narrated BEGIN/END markers."""
    import json
    import time

    client = BreakpointGdbClient(host, port)
    events: list[dict] = []
    t0 = time.monotonic()
    try:
        print(f"connected to GDB stub at {host}:{port}", file=sys.stderr)
        for addr in targets:
            if not client.set_breakpoint(addr):
                print(f"FAILED to arm 0x{addr:08X}", file=sys.stderr)
                return False
        print(f"armed {len(targets)} candidate target(s); logging for up to {total_timeout:.0f}s...", file=sys.stderr)
        deadline = t0 + total_timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                print("total timeout reached", file=sys.stderr)
                break
            reply = client.continue_and_wait_for_stop(remaining)
            if not reply:
                print("no more stops (timeout)", file=sys.stderr)
                break
            t = time.monotonic() - t0
            regs = client.read_registers()
            if regs is None or len(regs) < (REG_PC_INDEX + 1) * 4:
                continue
            pc = _parse_reg(regs, REG_PC_INDEX)
            events.append({"t": round(t, 3), "pc": hex(pc)})
        with open(out_path, "w") as f:
            json.dump(events, f, indent=2)
        print(f"wrote {len(events)} hit(s) to {out_path}", file=sys.stderr)
        for addr in targets:
            client.remove_breakpoint(addr)
        return True
    finally:
        client.close()


def sample_pc_profile(
    out_path: str,
    host: str = "127.0.0.1",
    port: int = 3334,
    total_timeout: float = 120.0,
    sample_interval: float = 0.1,
) -> bool:
    """Statistical sampling profiler: NO breakpoints armed at all, so no
    per-instruction checking overhead and no risk of the interpreter
    slowdown found when arming 890 simultaneous exec breakpoints.
    Instead, periodically sends GDB's raw interrupt byte (0x03), reads
    $pc from the resulting stop-reply's registers, then immediately
    resumes with 'c'. Between samples the CPU runs completely freely.
    Builds a list of (timestamp, pc) samples; which functions are
    "hot" during a given window is inferred from sample density there,
    the same technique real statistical profilers (perf, py-spy) use."""
    import json
    import time

    client = BreakpointGdbClient(host, port)
    samples: list[dict] = []
    t0 = time.monotonic()
    try:
        print(f"connected to GDB stub at {host}:{port}", file=sys.stderr)
        # 'c' (resume) produces NO reply of its own -- the next reply
        # only arrives when something next stops the target (here, our
        # own next interrupt byte below). Sending it is fire-and-forget.
        client._send(b"c")
        print(f"sampling every {sample_interval*1000:.0f}ms for up to {total_timeout:.0f}s (no breakpoints armed)...", file=sys.stderr)
        deadline = t0 + total_timeout
        while time.monotonic() < deadline:
            time.sleep(sample_interval)
            t = time.monotonic() - t0
            client._sock.settimeout(5.0)
            client._sock.sendall(b"\x03")
            reply = _read_reply_skip_console(client)
            if not reply:
                continue
            regs = client.read_registers()
            # The regular $pc (index 37) always reads as the exception
            # vector entry (0x80000080) when interrupted this way -- the
            # BIOS exception handler's own prologue stashes the real
            # interrupted PC (EPC) into $k0 (GPR 26) as its standard
            # convention, confirmed this session by observing real,
            # varying CAP0.EXE-range addresses there across samples.
            if regs is not None and len(regs) >= 27 * 4:
                pc = _parse_reg(regs, 26)
                samples.append({"t": round(t, 3), "pc": hex(pc)})
            client._send(b"c")  # resume; fire-and-forget, no reply expected
        with open(out_path, "w") as f:
            json.dump(samples, f, indent=2)
        print(f"wrote {len(samples)} sample(s) to {out_path}", file=sys.stderr)
        return True
    finally:
        client.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--addr", type=lambda s: int(s, 0), default=0x80081BB8)
    parser.add_argument("--out", default="cdinit_gdb_trigger.bin")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3334)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--watch", action="store_true", help="write watchpoint instead of exec breakpoint")
    parser.add_argument("--length", type=int, default=4, help="watchpoint length in bytes")
    parser.add_argument("--sequence", action="store_true", help="log every hit over --timeout seconds instead of stopping at the first one")
    parser.add_argument("--commands", action="store_true", help="log CD command bytes at all known command-issuing sites")
    parser.add_argument("--spu-mmio", action="store_true", help="watch SPU Transfer Address/Data FIFO registers")
    parser.add_argument("--spu-upload", action="store_true", help="log exact SPU Transfer Address/FIFO write sites with overlay+LBA context")
    parser.add_argument("--cd-data-stream", action="store_true", help="reconstruct the CD Data FIFO byte stream correlated with command sites")
    args = parser.parse_args(argv)

    if args.cd_data_stream:
        ok = log_cd_data_stream(args.out, args.host, args.port, args.timeout)
    elif args.spu_upload:
        ok = log_spu_upload_events(args.out, args.host, args.port, args.timeout)
    elif args.spu_mmio:
        ok = log_spu_mmio_watchpoints(args.out, args.host, args.port, args.timeout)
    elif args.commands:
        ok = log_command_sequence(CD_COMMAND_SITES, args.out, args.host, args.port, args.timeout)
    elif args.sequence:
        ok = log_watchpoint_sequence(args.addr, args.length, args.out, args.host, args.port, args.timeout)
    elif args.watch:
        ok = capture_on_write_watchpoint(args.addr, args.length, args.out, args.host, args.port, args.timeout)
    else:
        ok = capture_on_breakpoint(args.addr, args.out, args.host, args.port, args.timeout)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
