"""Tests for gcrts.pcsx_pad_bridge's pure file-protocol and reload/
retry logic. The actual live wait-for-Lua-ack behavior and the real
gcrts.pcsx_lua_console.run_lua call are inherently untestable without a
running PCSX-Redux instance (same convention as this project's other
live/GUI modules) and are exercised manually -- every test here injects
a fake `run_lua` so no real OS input is ever sent."""
from __future__ import annotations

import json

import pytest

import gcrts.pcsx_pad_bridge as mod
from gcrts.pcsx_pad_bridge import PadBridgeClient, PadBridgeTimeout, PadBridgeUnknownButton


def _client(tmp_path, monkeypatch, fixed_time=1234.0, run_lua=None):
    monkeypatch.setattr(mod.time, "time", lambda: fixed_time)
    if run_lua is None:
        run_lua = lambda code: None  # noqa: E731
    return PadBridgeClient(command_path=tmp_path / "cmd.jsonl", ack_path=tmp_path / "ack.jsonl", run_lua=run_lua)


def test_press_button_writes_command_file_and_returns_on_matching_ack(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, fixed_time=1234.0)
    client.ack_path.write_text(json.dumps({"id": int(1234.0 * 1000), "done": True}) + "\n", encoding="utf-8")

    client.press_button("CIRCLE", hold_frames=5, timeout_seconds=2.0)

    command = json.loads(client.command_path.read_text(encoding="utf-8"))
    assert command["button"] == "CIRCLE"
    assert command["hold_frames"] == 5
    assert command["id"] == int(1234.0 * 1000)


def test_press_button_lowercase_is_normalized(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, fixed_time=5678.0)
    client.ack_path.write_text(json.dumps({"id": int(5678.0 * 1000), "done": True}) + "\n", encoding="utf-8")

    client.press_button("circle", timeout_seconds=2.0)  # must not raise
    command = json.loads(client.command_path.read_text(encoding="utf-8"))
    assert command["button"] == "CIRCLE"


def test_press_button_rejects_unknown_button(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    with pytest.raises(PadBridgeUnknownButton):
        client.press_button("HYPERBUTTON")


def test_press_button_times_out_when_no_ack_ever_arrives(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    with pytest.raises(PadBridgeTimeout):
        client.press_button("CIRCLE", timeout_seconds=0.2)


def test_press_button_does_not_call_run_lua_when_allow_reload_is_false(tmp_path, monkeypatch):
    calls = []
    client = _client(tmp_path, monkeypatch, run_lua=lambda code: calls.append(code))
    with pytest.raises(PadBridgeTimeout):
        client.press_button("CIRCLE", timeout_seconds=0.2, allow_reload=False)
    assert calls == []


def test_press_button_reloads_and_retries_once_on_timeout(tmp_path, monkeypatch):
    calls = []

    def fake_run_lua(code):
        calls.append(code)
        # Simulate the reloaded listener now acking any pending command.
        last_command = json.loads(client.command_path.read_text(encoding="utf-8"))
        client.ack_path.write_text(json.dumps({"id": last_command["id"], "done": True}) + "\n", encoding="utf-8")

    client = _client(tmp_path, monkeypatch, run_lua=fake_run_lua)
    client.press_button("CIRCLE", timeout_seconds=0.2)

    assert calls == [mod.BRIDGE_SCRIPT_DOFILE]


def test_press_button_raises_if_still_no_ack_after_reload(tmp_path, monkeypatch):
    calls = []
    client = _client(tmp_path, monkeypatch, run_lua=lambda code: calls.append(code))
    with pytest.raises(PadBridgeTimeout, match="after reloading"):
        client.press_button("CIRCLE", timeout_seconds=0.2)
    assert calls == [mod.BRIDGE_SCRIPT_DOFILE]


def test_last_ack_id_ignores_malformed_lines_and_takes_max(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.ack_path.write_text('{"id":1,"done":true}\nnot json\n{"id":5,"done":true}\n{"id":3,"done":true}\n', encoding="utf-8")
    assert client._last_ack_id() == 5


def test_last_ack_id_returns_zero_when_file_missing(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    assert client._last_ack_id() == 0


def test_default_run_lua_is_lazily_bound_to_real_module(tmp_path):
    # No monkeypatching here -- confirms __post_init__ resolves the
    # real gcrts.pcsx_lua_console.run_lua without invoking it or
    # requiring a live PCSX-Redux instance.
    from gcrts.pcsx_lua_console import run_lua as real_run_lua

    client = PadBridgeClient(command_path=tmp_path / "cmd.jsonl", ack_path=tmp_path / "ack.jsonl")
    assert client.run_lua is real_run_lua
