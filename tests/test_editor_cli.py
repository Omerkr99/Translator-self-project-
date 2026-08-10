import struct

from gcrts.editor_cli import EditorCLI
from gcrts.editor_state import EditorState, UnitStatus
from gcrts.script_decoder import decode_script
from gcrts.script_unit import units_from_script_document


def _pack(words):
    return struct.pack(f"<{len(words)}H", *words)


def _cli_with_sample_units():
    doc = decode_script(_pack([0x0001, 0x0002, 0x8500, 0x0300, 0xFFFF]))
    units = units_from_script_document(doc, scene_id="scene")
    state = EditorState()
    state.load_units(units)
    return EditorCLI(state)


def test_do_list_shows_loaded_units(capsys):
    cli = _cli_with_sample_units()
    cli.do_list("")
    out = capsys.readouterr().out
    for u in cli.state.units:
        assert u.id in out


def test_do_edit_updates_state_and_reports_status(capsys):
    cli = _cli_with_sample_units()
    unit_id = cli.state.units[0].id
    cli.do_edit(f"{unit_id} hello there")
    assert cli.state.get(unit_id).edited_text == "hello there"
    out = capsys.readouterr().out
    assert "modified" in out


def test_do_edit_unknown_id_reports_error(capsys):
    cli = _cli_with_sample_units()
    cli.do_edit("nope some text")
    out = capsys.readouterr().out
    assert "no such unit" in out


def test_do_reset_reverts_text(capsys):
    cli = _cli_with_sample_units()
    unit_id = cli.state.units[0].id
    original = cli.state.get(unit_id).original_text
    cli.do_edit(f"{unit_id} changed")
    cli.do_reset(unit_id)
    assert cli.state.get(unit_id).edited_text == original


def test_do_revert_is_an_alias_for_reset(capsys):
    cli = _cli_with_sample_units()
    unit_id = cli.state.units[0].id
    original = cli.state.get(unit_id).original_text
    cli.do_edit(f"{unit_id} changed")
    cli.do_revert(unit_id)
    assert cli.state.get(unit_id).edited_text == original


def test_do_boundary_shows_offsets_and_contiguity(capsys):
    cli = _cli_with_sample_units()
    unit = cli.state.units[0]
    cli.do_boundary(unit.id)
    out = capsys.readouterr().out
    assert str(unit.unit_start_offset) in out
    assert str(unit.unit_end_offset) in out
    assert str(unit.contiguous_with_next()) in out


def test_do_boundary_unknown_id_reports_error(capsys):
    cli = _cli_with_sample_units()
    cli.do_boundary("nope")
    out = capsys.readouterr().out
    assert "no such unit" in out


def test_do_show_includes_boundary_line(capsys):
    cli = _cli_with_sample_units()
    unit_id = cli.state.units[0].id
    cli.do_show(unit_id)
    out = capsys.readouterr().out
    assert "boundary:" in out
    assert "contiguous=" in out


def test_do_filter_missing(capsys):
    cli = _cli_with_sample_units()
    cli.do_filter("missing")
    out = capsys.readouterr().out
    missing_ids = [u.id for u in cli.state.units if u.missing_glyphs]
    for uid in missing_ids:
        assert uid in out


def test_do_show_prints_detail_fields(capsys):
    cli = _cli_with_sample_units()
    unit_id = cli.state.units[0].id
    cli.do_show(unit_id)
    out = capsys.readouterr().out
    assert "raw_codes:" in out
    assert "control_events:" in out
    assert "missing_glyphs:" in out


def test_do_save_and_load_roundtrip(tmp_path):
    cli = _cli_with_sample_units()
    unit_id = cli.state.units[0].id
    cli.do_edit(f"{unit_id} persisted text")

    path = str(tmp_path / "session.json")
    cli.do_save(path)

    cli2 = EditorCLI()
    cli2.do_load(path)
    assert cli2.state.get(unit_id).edited_text == "persisted text"


def test_do_quit_returns_true_to_stop_cmdloop():
    cli = _cli_with_sample_units()
    assert cli.do_quit("") is True


# --- Alternative Text Engine, Phase 3: layout_* commands -----------------


def test_do_layout_mode_switches_render_mode(capsys):
    from gcrts.render_mode import RenderMode

    cli = _cli_with_sample_units()
    unit_id = cli.state.units[0].id
    cli.do_layout_mode(f"{unit_id} custom_engine")
    assert cli.state.get(unit_id).render_mode == RenderMode.CUSTOM_ENGINE
    assert "custom_engine" in capsys.readouterr().out


def test_do_layout_mode_rejects_an_unknown_mode(capsys):
    cli = _cli_with_sample_units()
    unit_id = cli.state.units[0].id
    cli.do_layout_mode(f"{unit_id} not_a_real_mode")
    assert "unknown render mode" in capsys.readouterr().out


def test_do_layout_auto_builds_a_plan_and_switches_mode(capsys):
    from gcrts.render_mode import RenderMode

    cli = _cli_with_sample_units()
    unit_id = cli.state.units[0].id
    cli.do_edit(f"{unit_id} hello world this is a test")
    capsys.readouterr()  # discard the edit's own output

    cli.do_layout_auto(f"{unit_id} 48")  # tiny budget forces multiple lines
    unit = cli.state.get(unit_id)
    assert unit.render_mode == RenderMode.CUSTOM_ENGINE
    assert unit.layout_plan is not None
    assert len(unit.layout_plan.lines) > 1
    out = capsys.readouterr().out
    assert "CUSTOM_ENGINE plan" in out or "line" in out


def test_do_layout_show_reports_no_plan_before_layout_auto(capsys):
    cli = _cli_with_sample_units()
    unit_id = cli.state.units[0].id
    cli.do_layout_show(unit_id)
    assert "no layout plan" in capsys.readouterr().out


def test_do_layout_add_update_remove_line_roundtrip(capsys):
    cli = _cli_with_sample_units()
    unit_id = cli.state.units[0].id
    cli.do_edit(f"{unit_id} hello")
    cli.do_layout_auto(unit_id)
    capsys.readouterr()

    cli.do_layout_add_line(f"{unit_id} 10 200 center a new line")
    plan = cli.state.get_layout_plan(unit_id)
    assert plan.lines[-1].text == "a new line"
    assert plan.lines[-1].alignment.value == "center"

    last_index = len(plan.lines) - 1
    cli.do_layout_update_line(f"{unit_id} {last_index} x 99")
    assert plan.lines[last_index].x == 99

    cli.do_layout_remove_line(f"{unit_id} {last_index}")
    assert len(plan.lines) == last_index


def test_do_layout_add_line_requires_an_existing_plan(capsys):
    cli = _cli_with_sample_units()
    unit_id = cli.state.units[0].id
    cli.do_layout_add_line(f"{unit_id} 10 160 left some text")
    assert "no layout plan yet" in capsys.readouterr().out


def test_do_layout_preview_reports_fits_for_a_clean_plan(capsys):
    cli = _cli_with_sample_units()
    unit_id = cli.state.units[0].id
    cli.do_edit(f"{unit_id} hi")
    cli.do_layout_auto(unit_id)
    capsys.readouterr()

    cli.do_layout_preview(unit_id)
    out = capsys.readouterr().out
    assert "fits=" in out


def test_layout_plan_persists_through_do_save_and_do_load(tmp_path):
    cli = _cli_with_sample_units()
    unit_id = cli.state.units[0].id
    cli.do_edit(f"{unit_id} hello there")
    cli.do_layout_auto(unit_id)

    path = str(tmp_path / "session.json")
    cli.do_save(path)

    cli2 = EditorCLI()
    cli2.do_load(path)
    restored_plan = cli2.state.get_layout_plan(unit_id)
    assert restored_plan is not None
    assert restored_plan.lines[0].text == "hello there"


def test_do_layout_render_writes_a_real_png_file(tmp_path, capsys):
    cli = _cli_with_sample_units()
    unit_id = cli.state.units[0].id
    cli.do_edit(f"{unit_id} hi")
    cli.do_layout_auto(unit_id)
    capsys.readouterr()

    out_path = str(tmp_path / "preview.png")
    cli.do_layout_render(f"{unit_id} {out_path}")
    assert "rendered to" in capsys.readouterr().out

    import pathlib

    p = pathlib.Path(out_path)
    assert p.exists()
    assert p.stat().st_size > 0


def test_do_layout_render_requires_an_existing_plan(capsys):
    cli = _cli_with_sample_units()
    unit_id = cli.state.units[0].id
    cli.do_layout_render(f"{unit_id} /tmp/whatever.png")
    assert "no layout plan yet" in capsys.readouterr().out
