"""Tests for gcrts.pcsx_keyboard_input -- the VK-mapping/flag logic is
tested directly; the actual Win32 SendInput/window calls are inherently
untestable without a live Windows desktop session (same convention as
this project's other live/GUI modules) and are exercised manually."""
from __future__ import annotations

import gcrts.pcsx_keyboard_input as mod
from gcrts.pcsx_keyboard_input import DEFAULT_VK_MAP, PadButton, press_button


def test_every_pad_button_has_a_vk_mapping():
    for button in PadButton:
        assert button in DEFAULT_VK_MAP, f"{button} missing from DEFAULT_VK_MAP"


def test_vk_codes_are_unique_per_button():
    codes = list(DEFAULT_VK_MAP.values())
    assert len(codes) == len(set(codes)), "two PadButtons map to the same VK code"


def test_letter_key_bindings_match_pcsx_json_ascii_convention():
    # pcsx.json's GLFW key codes for these bindings numerically equal
    # the ASCII/VK code for the letter -- confirmed this session
    # (Keyboard_PadCircle=68='D', Keyboard_PadCross=88='X', etc.)
    assert DEFAULT_VK_MAP[PadButton.CIRCLE] == 0x44  # 'D'
    assert DEFAULT_VK_MAP[PadButton.CROSS] == 0x58  # 'X'
    assert DEFAULT_VK_MAP[PadButton.SQUARE] == 0x5A  # 'Z'
    assert DEFAULT_VK_MAP[PadButton.TRIANGLE] == 0x53  # 'S'


def test_arrow_keys_are_flagged_extended():
    for button in (PadButton.UP, PadButton.DOWN, PadButton.LEFT, PadButton.RIGHT):
        assert button in mod._EXTENDED_KEYS


def test_letter_and_start_select_buttons_are_not_extended():
    for button in (PadButton.CIRCLE, PadButton.CROSS, PadButton.SQUARE, PadButton.TRIANGLE, PadButton.START, PadButton.SELECT):
        assert button not in mod._EXTENDED_KEYS


def test_press_button_sends_key_down_then_key_up_with_correct_extended_flag(monkeypatch):
    calls = []

    def fake_send(vk, key_up, extended):
        calls.append((vk, key_up, extended))

    monkeypatch.setattr(mod, "_send_key_event", fake_send)
    press_button(PadButton.RIGHT, hold_seconds=0)

    assert len(calls) == 2
    assert calls[0] == (DEFAULT_VK_MAP[PadButton.RIGHT], False, True)  # key down, extended
    assert calls[1] == (DEFAULT_VK_MAP[PadButton.RIGHT], True, True)  # key up, extended


def test_press_button_letter_key_is_not_extended(monkeypatch):
    calls = []
    monkeypatch.setattr(mod, "_send_key_event", lambda vk, key_up, extended: calls.append((vk, key_up, extended)))
    press_button(PadButton.CIRCLE, hold_seconds=0)
    assert calls[0][2] is False
    assert calls[1][2] is False
