"""PCSX-Redux implementation of `gcrts.emulator_adapter.EmulatorAdapter`
-- the first (and, per the overlay-engine spec, reference) adapter for
the external overlay/test-runner subsystem
(`docs/overlay_engine/PS1_OVERLAY_RUNTIME_SYSTEM_DESIGN.md` §4).

Wraps this project's own already-proven live-transport pieces rather
than reimplementing them: `gcrts.gdb_client.GdbClient` for memory/
breakpoints (the same client this session used repeatedly, live,
against the real emulator), and the PCSX-Redux Web API's
`/api/v1/gpu/vram/raw` (screenshot, same decode as
`gcrts.screen_capture.PcsxVramCaptureProvider`) and `/api/v1/state/load`
(save-state loading, used throughout this project's own movie/audio
investigations) endpoints directly.

Honest capability advertisement (EMU-004,
`docs/status/TOOLKIT_READINESS_AUDIT.md`): `FRAME_COUNTER` and
`AUDIO_CONTROL` are deliberately NOT included in `capabilities()` --
no real endpoint or mechanism for either has been proven working in
this project. `load_state` takes a `slot: int`, not an arbitrary file
path -- the real PCSX-Redux Web API is slot-based
(`/api/v1/state/load?slot=N`), and this adapter is grounded in that
reality rather than the interface's more generic pseudocode.
"""
from __future__ import annotations

import urllib.request

from PIL import Image

from gcrts.emulator_adapter import EmulatorAdapter, EmulatorCapabilities, EmulatorCapability
from gcrts.gdb_client import GdbClient

_ADVERTISED_CAPABILITIES = frozenset(
    {
        EmulatorCapability.MEMORY_READ,
        EmulatorCapability.MEMORY_WRITE,
        EmulatorCapability.BREAKPOINTS,
        EmulatorCapability.SCREENSHOT,
        EmulatorCapability.SAVE_STATE_LOAD,
        EmulatorCapability.PAUSE_RESUME,
    }
)


class PCSXReduxAdapter(EmulatorAdapter):
    def __init__(
        self,
        gdb_host: str = "127.0.0.1",
        gdb_port: int = 3334,
        api_base_url: str = "http://127.0.0.1:8080",
        connect: bool = True,
    ):
        self.api_base_url = api_base_url.rstrip("/")
        self._gdb_host = gdb_host
        self._gdb_port = gdb_port
        self._client: GdbClient | None = None
        if connect:
            self._client = GdbClient(gdb_host, gdb_port)

    def _require_client(self) -> GdbClient:
        if self._client is None:
            self._client = GdbClient(self._gdb_host, self._gdb_port)
        return self._client

    def capabilities(self) -> EmulatorCapabilities:
        return EmulatorCapabilities(supported=_ADVERTISED_CAPABILITIES)

    def read_memory(self, addr: int, length: int) -> bytes | None:
        return self._require_client().read_memory(addr, length)

    def write_memory(self, addr: int, data: bytes) -> bool:
        return self._require_client().write_memory(addr, data)

    def set_breakpoint(self, addr: int) -> bool:
        return self._require_client().set_breakpoint(addr)

    def clear_breakpoint(self, addr: int) -> bool:
        return self._require_client().remove_breakpoint(addr)

    def screenshot(self, region: tuple[int, int, int, int] = (0, 0, 320, 240)) -> Image.Image:
        """Decodes the real live VRAM dump the same way
        `gcrts.screen_capture.PcsxVramCaptureProvider` does -- kept as
        a separate small implementation here (rather than importing
        that class directly) so this adapter has no dependency beyond
        the Web API itself; the two are expected to stay in sync."""
        with urllib.request.urlopen(f"{self.api_base_url}/api/v1/gpu/vram/raw", timeout=10) as response:
            raw = response.read()
        if len(raw) != 1024 * 512 * 2:
            raise ValueError(f"unexpected VRAM dump length {len(raw)}")
        x0, y0, width, height = region
        image = Image.new("RGB", (width, height))
        pixels = []
        for y in range(y0, y0 + height):
            for x in range(x0, x0 + width):
                p = 2 * (y * 1024 + x)
                value = raw[p] | raw[p + 1] << 8
                pixels.append(((value & 31) * 255 // 31, ((value >> 5) & 31) * 255 // 31, ((value >> 10) & 31) * 255 // 31))
        image.putdata(pixels)
        return image

    def load_state(self, slot: int) -> bool:
        request = urllib.request.Request(f"{self.api_base_url}/api/v1/state/load?slot={slot}", method="GET")
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status == 200

    def pause(self) -> None:
        self._require_client().interrupt()

    def resume(self) -> None:
        self._require_client().resume()

    def shutdown(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
