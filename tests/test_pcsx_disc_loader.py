"""Pure-logic tests for gcrts.pcsx_disc_loader -- the live GUI
automation itself (mouse clicks, window lookup) is manually verified
only, per this project's convention for live/external-tool modules."""
from __future__ import annotations

from gcrts.pcsx_disc_loader import FIRST_ROW_CENTER_Y, ROW_HEIGHT, _row_index_for_filename


def test_row_index_matches_case_insensitive_alphabetical_order(tmp_path):
    # Mirrors the real 10-file listing this was verified against live:
    # deliberately out of creation/insertion order to prove sorting, not
    # listing order, drives the result.
    names = [
        "SCPH1001.BIN",
        "game.cue",
        "font_fix_demo.bin",
        "game.bin",
        "op_title_card_demo.cue",
        "game_persistent_test.cue",
        "font_fix_demo.cue",
        "op_title_card_demo.bin",
        "game.bin.original_backup",
        "game_persistent_test.bin",
    ]
    for name in names:
        (tmp_path / name).write_bytes(b"")

    assert _row_index_for_filename(str(tmp_path), "font_fix_demo.bin") == 0
    assert _row_index_for_filename(str(tmp_path), "font_fix_demo.cue") == 1
    assert _row_index_for_filename(str(tmp_path), "game.bin") == 2
    assert _row_index_for_filename(str(tmp_path), "game.bin.original_backup") == 3
    assert _row_index_for_filename(str(tmp_path), "game.cue") == 4
    assert _row_index_for_filename(str(tmp_path), "game_persistent_test.bin") == 5
    assert _row_index_for_filename(str(tmp_path), "game_persistent_test.cue") == 6
    assert _row_index_for_filename(str(tmp_path), "op_title_card_demo.bin") == 7
    assert _row_index_for_filename(str(tmp_path), "op_title_card_demo.cue") == 8
    assert _row_index_for_filename(str(tmp_path), "SCPH1001.BIN") == 9


def test_row_index_raises_for_a_missing_file(tmp_path):
    (tmp_path / "only_file.bin").write_bytes(b"")
    try:
        _row_index_for_filename(str(tmp_path), "not_there.bin")
        assert False, "expected ValueError for a filename not in the directory"
    except ValueError:
        pass


def test_row_pixel_geometry_matches_the_live_measurement_used_to_derive_it():
    # game.bin.original_backup was row index 3 in the real 10-file
    # listing this was measured against, and its selected-row highlight
    # was observed spanning y=151-170 (center 160.5) in a real capture.
    row_index = 3
    measured_center_y = FIRST_ROW_CENTER_Y + row_index * ROW_HEIGHT
    assert abs(measured_center_y - 160.5) <= 1.0
