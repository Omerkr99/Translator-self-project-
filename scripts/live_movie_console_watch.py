"""Long-running passive listener for the two movie-player overlay groups
still only resolvable to an ambiguous 2-3 file candidate set
(`"MKUBI.EXE (or MNINO.EXE/MRIKA.EXE)"` and `MOVER.EXE`) --
`gcrts.movie_detection.AMBIGUOUS_GROUPS`. `MPRO.EXE`/`MYOKO.EXE` and
`MOP.EXE` are already resolved (see docs/renderer/MOVIE_DETECTION.md);
a full sweep of every existing save slot (0-9) found none of them land
on a boundary that auto-triggers either remaining group on load, unlike
save slot 6 for MPRO.EXE -- so this listener has to stay armed across
an actual play session instead of a single instant load.

Arms exec breakpoints at both groups' real entry PCs
(`gcrts.overlay_identity.KNOWN_OVERLAYS`) and keeps continuing after
every hit, capturing the kernel's own console text in between (the
"(Movie)Load Exec : \\NAME.EXE;1" debug line, forwarded over GDB's
async 'O' packets) so `gcrts.movie_detection.parse_exec_load_name()`
and `resolve_ambiguous_group_via_console_text()` can name the exact
executable the instant either group loads -- no polling interval to
straddle, no RAM-diffing needed.

Usage:
    python -m scripts.live_movie_console_watch --out overlay_watch_console.json --timeout 600
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
import time

from gcrts.movie_detection import parse_exec_load_name, resolve_ambiguous_group_via_console_text
from gcrts.overlay_identity import KNOWN_OVERLAYS
from scripts.gdb_cdinit_trigger_capture import BreakpointGdbClient

# Only the two groups not yet resolved to a single confirmed file.
_UNRESOLVED_NAMES = {
    "MKUBI.EXE (or MNINO.EXE/MRIKA.EXE)",
    "MOVER.EXE",
}
TARGETS: dict[int, str] = {
    profile.pc0: profile.name for profile in KNOWN_OVERLAYS if profile.name in _UNRESOLVED_NAMES
}


def _continue_and_wait_with_console(client: BreakpointGdbClient, timeout: float) -> tuple[str, list[str]]:
    """Same as BreakpointGdbClient.continue_and_wait_for_stop but also
    returns the accumulated console (O-packet) text lines seen while
    waiting, instead of just printing and discarding them."""
    lines: list[str] = []
    old_timeout = client._sock.gettimeout()
    deadline = time.monotonic() + timeout
    client._sock.settimeout(timeout)
    try:
        client._send(b"c")
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return "", lines
            client._sock.settimeout(remaining)
            try:
                reply = client._read_reply()
            except (socket.timeout, TimeoutError):
                return "", lines
            if not reply:
                return "", lines
            if reply.startswith("O"):
                try:
                    text = bytes.fromhex(reply[1:]).decode(errors="replace")
                except ValueError:
                    text = reply[1:]
                lines.append(text)
                continue
            return reply, lines
    finally:
        client._sock.settimeout(old_timeout)


def watch(out_path: str, host: str = "127.0.0.1", port: int = 3334, total_timeout: float = 600.0) -> bool:
    client = BreakpointGdbClient(host, port)
    events: list[dict] = []
    t0 = time.monotonic()
    try:
        for addr, name in TARGETS.items():
            ok = client.set_breakpoint(addr)
            print(f"armed 0x{addr:08X} ({name}): {ok}", file=sys.stderr, flush=True)
            if not ok:
                return False
        print(f"watching for up to {total_timeout:.0f}s -- play forward now...", file=sys.stderr, flush=True)
        deadline = t0 + total_timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                print("total timeout reached, no hit", file=sys.stderr, flush=True)
                break
            reply, console_lines = _continue_and_wait_with_console(client, remaining)
            if not reply:
                break
            t = time.monotonic() - t0
            exec_name = None
            for line in console_lines:
                n = parse_exec_load_name(line)
                if n:
                    exec_name = n
            resolved = None
            for overlay_name in _UNRESOLVED_NAMES:
                if exec_name is not None:
                    resolved = resolve_ambiguous_group_via_console_text(overlay_name, exec_name)
                    if resolved is not None:
                        break
            event = {
                "t": round(t, 2),
                "console_lines": console_lines,
                "parsed_exec_name": exec_name,
                "resolved": resolved,
            }
            events.append(event)
            print(f"[t={t:7.2f}s] HIT -- exec_name={exec_name} resolved={resolved}", file=sys.stderr, flush=True)
            print(f"  console: {console_lines}", file=sys.stderr, flush=True)
        with open(out_path, "w") as f:
            json.dump(events, f, indent=2)
        print(f"wrote {len(events)} event(s) to {out_path}", file=sys.stderr, flush=True)
        for addr in TARGETS:
            client.remove_breakpoint(addr)
        return True
    finally:
        client.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="overlay_watch_console.json")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3334)
    parser.add_argument("--timeout", type=float, default=600.0)
    args = parser.parse_args(argv)
    ok = watch(args.out, args.host, args.port, args.timeout)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
