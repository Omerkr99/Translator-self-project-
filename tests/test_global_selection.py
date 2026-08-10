from pathlib import Path

import pytest

from gcrts.asset_inspector_ui import resolve_asset_selection, runtime_status_text
from gcrts.asset_project import AssetProject

ROOT = Path(__file__).parents[1] / "sdb_main_menu_asset"


@pytest.mark.skipif(not (ROOT / "MENUDAT.BIN").exists(), reason="verified asset fixture not present")
def test_resolve_known_block_asset():
    project = AssetProject.open(ROOT / "MENUDAT.BIN", "DAT/SINKOU/MENUDAT.BIN;1")
    assert resolve_asset_selection(project, (), "main_menu.start") == ("block", 7)
    assert resolve_asset_selection(project, (), "main_menu.prepare") == ("block", 8)


@pytest.mark.skipif(not (ROOT / "PROGDAT.BIN").exists(), reason="verified asset fixture not present")
def test_resolve_composite_asset():
    project = AssetProject.open(ROOT / "PROGDAT.BIN", "DAT/SINKOU/PROGDAT.BIN;1")
    assert resolve_asset_selection(project, (0, 1, 2, 3, 4), "progdat.group0") == ("composite", None)


@pytest.mark.skipif(not (ROOT / "PROGDAT.BIN").exists(), reason="verified asset fixture not present")
def test_resolve_composite_asset_wrong_group_number_is_unknown():
    project = AssetProject.open(ROOT / "PROGDAT.BIN", "DAT/SINKOU/PROGDAT.BIN;1")
    assert resolve_asset_selection(project, (0, 1, 2, 3, 4), "progdat.group2") is None


@pytest.mark.skipif(not (ROOT / "MENUDAT.BIN").exists(), reason="verified asset fixture not present")
def test_resolve_unknown_asset_id_is_none_not_a_guess():
    project = AssetProject.open(ROOT / "MENUDAT.BIN", "DAT/SINKOU/MENUDAT.BIN;1")
    assert resolve_asset_selection(project, (), "progdat.group0") is None
    assert resolve_asset_selection(project, (), "totally.unknown.asset") is None


def test_runtime_status_text_reflects_live_set():
    assert runtime_status_text("main_menu.start", {"main_menu.start", "main_menu.prepare"}) == "LIVE -- currently drawn this frame"
    assert runtime_status_text("main_menu.start", set()) == "Known asset -- not currently drawn"
