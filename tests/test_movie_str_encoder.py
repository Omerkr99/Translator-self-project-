"""Tests for gcrts.movie_str_encoder -- exercises the subprocess
argument construction and error handling with a monkeypatched
subprocess.run, since the real psxavenc.exe is a third-party binary
not vendored in this repo (see module docstring for where to get it).
No live dependency."""
from __future__ import annotations

import pytest

import gcrts.movie_str_encoder as mod
from gcrts.movie_str_encoder import PsxavencError, encode_str


class _FakeResult:
    def __init__(self, returncode, stderr=""):
        self.returncode = returncode
        self.stderr = stderr


def test_encode_str_builds_correct_command(monkeypatch, tmp_path):
    captured = {}

    def fake_run(cmd, capture_output, text):
        captured["cmd"] = cmd
        return _FakeResult(0)

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    encode_str("C:/tools/psxavenc.exe", tmp_path / "in.mkv", tmp_path / "out.str")

    cmd = captured["cmd"]
    assert cmd[0] == "C:/tools/psxavenc.exe"
    assert "-t" in cmd and cmd[cmd.index("-t") + 1] == "strcd"
    assert "-f" in cmd and cmd[cmd.index("-f") + 1] == "37800"
    assert "-c" in cmd and cmd[cmd.index("-c") + 1] == "2"
    assert "-s" in cmd and cmd[cmd.index("-s") + 1] == "320x240"
    assert "-r" in cmd and cmd[cmd.index("-r") + 1] == "15"
    assert str(tmp_path / "in.mkv") in cmd
    assert str(tmp_path / "out.str") in cmd


def test_encode_str_respects_custom_options(monkeypatch, tmp_path):
    captured = {}

    def fake_run(cmd, capture_output, text):
        captured["cmd"] = cmd
        return _FakeResult(0)

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    encode_str(
        "psxavenc.exe", tmp_path / "in.mkv", tmp_path / "out.str",
        sample_rate=18900, channels=1, size="160x120", fps=10, format="str",
    )

    cmd = captured["cmd"]
    assert cmd[cmd.index("-t") + 1] == "str"
    assert cmd[cmd.index("-f") + 1] == "18900"
    assert cmd[cmd.index("-c") + 1] == "1"
    assert cmd[cmd.index("-s") + 1] == "160x120"
    assert cmd[cmd.index("-r") + 1] == "10"


def test_encode_str_raises_on_nonzero_exit(monkeypatch, tmp_path):
    def fake_run(cmd, capture_output, text):
        return _FakeResult(1, stderr="something went wrong")

    monkeypatch.setattr(mod.subprocess, "run", fake_run)

    with pytest.raises(PsxavencError, match="something went wrong"):
        encode_str("psxavenc.exe", tmp_path / "in.mkv", tmp_path / "out.str")
