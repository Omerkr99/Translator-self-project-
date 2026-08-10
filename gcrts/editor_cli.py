"""Live Text Workbench, Phase 2: terminal editor UI.

A thin renderer over gcrts.editor_state.EditorState -- every command here
just calls a state method and prints the result. No business logic lives
in this module; that keeps it swappable for a future desktop UI without
touching gcrts.editor_state at all.

Run interactively:
    py -m gcrts.editor_cli

Run against a live game session directly:
    py -m gcrts.editor_cli --extract scene_012 --host 127.0.0.1 --port 3333
"""
from __future__ import annotations

import argparse
import cmd

from gcrts.editor_state import EditorState, UnitStatus
from gcrts.font_workbench import GlyphAuditLog


def _preview(text: str, width: int = 40) -> str:
    text = text.replace("\n", " ")
    return text if len(text) <= width else text[: width - 1] + "…"


class EditorCLI(cmd.Cmd):
    intro = "Live Text Workbench editor. Type 'help' for commands, 'quit' to exit."
    prompt = "(workbench) "

    def __init__(self, state: EditorState | None = None):
        super().__init__()
        self.state = state or EditorState()
        self.glyph_log = GlyphAuditLog()

    # --- browsing -----------------------------------------------------

    def do_list(self, arg: str) -> None:
        """list [query] -- list all units, optionally filtered by a text search."""
        units = self.state.search(query=arg.strip()) if arg.strip() else self.state.units
        if not units:
            print("(no units loaded -- try 'extract <scene_id>' or 'load <path>')")
            return
        for u in units:
            status = self.state.status(u.id).value
            validation = self.state.validation_status(u.id)
            print(f"{u.id:24} [{status:10}] [{validation:14}] {u.text_type:10} {_preview(u.edited_text)!r}")

    def do_show(self, arg: str) -> None:
        """show <id> -- full detail for one unit, including its boundary
        range (see 'boundary <id>' for just that part)."""
        unit = self.state.get(arg.strip())
        if unit is None:
            print(f"no such unit: {arg!r}")
            return
        print(f"id:            {unit.id}")
        print(f"source:        {unit.source}")
        print(f"ram_address:   {hex(unit.ram_address) if unit.ram_address is not None else None}")
        print(f"boundary:      [{unit.unit_start_offset}, {unit.unit_end_offset}) "
              f"next_unit_start={unit.next_unit_start_offset} "
              f"contiguous={unit.contiguous_with_next()}")
        print(f"text_type:     {unit.text_type}")
        print(f"status:        {self.state.status(unit.id).value}")
        print(f"validation:    {self.state.validation_status(unit.id)} ({self.state.validation_detail(unit.id)})")
        print(f"original (JA): {unit.original_text!r}")
        print(f"edited   (EN): {unit.edited_text!r}")
        print(f"raw_codes:     {unit.raw_codes}")
        print("control_events:")
        for e in unit.control_events:
            print(f"  {e}")
        print(f"layout_constraints: {unit.layout_constraints}")
        print(f"glyphs_used:    {unit.glyphs_used}")
        print(f"missing_glyphs: {unit.missing_glyphs}")
        note = self.state.get_note(unit.id)
        if note:
            print(f"note: {note}")

    def do_boundary(self, arg: str) -> None:
        """boundary <id> -- just this unit's start/end/next-unit offsets
        and whether it's contiguous with what follows it. Nothing here is
        a warning yet (that's boundary VALIDATION, a later phase) -- this
        is only the raw boundary facts."""
        unit = self.state.get(arg.strip())
        if unit is None:
            print(f"no such unit: {arg!r}")
            return
        print(f"unit_start_offset:      {unit.unit_start_offset}")
        print(f"unit_end_offset:        {unit.unit_end_offset}")
        print(f"next_unit_start_offset: {unit.next_unit_start_offset}")
        print(f"contiguous_with_next:   {unit.contiguous_with_next()}")

    def do_check_boundary(self, arg: str) -> None:
        """check_boundary <id> -- warn if this unit's CURRENT edited_text
        would shift later units in the same buffer once re-injected, or
        if its boundary bookkeeping has drifted. Safe/no-op reporting --
        never blocks anything, just informs."""
        unit = self.state.get(arg.strip())
        if unit is None:
            print(f"no such unit: {arg!r}")
            return
        from gcrts.boundary_validation import check_boundary

        report = check_boundary(unit)
        print(f"original_word_count: {report.original_word_count}")
        print(f"new_word_count:      {report.new_word_count}")
        print(f"word_count_delta:    {report.word_count_delta}")
        print(f"shifts_subsequent:   {report.shifts_subsequent_units}")
        print(f"boundary_ok:         {report.boundary_bookkeeping_ok}")
        for w in report.warnings:
            print(f"warning: {w}")
        if not report.warnings:
            print("no boundary concerns")

    def do_check_chain(self, arg: str) -> None:
        """check_chain -- verify every currently loaded unit's end offset
        exactly meets the next unit's start offset, across the whole list."""
        from gcrts.boundary_validation import check_chain

        problems = check_chain(self.state.units)
        if not problems:
            print(f"chain OK across {len(self.state.units)} units")
            return
        for p in problems:
            print(f"problem: {p}")

    def do_fit(self, arg: str) -> None:
        """fit <id> [--pixel] [--center] [width_px] -- reflow the unit's
        edited_text into clean, word-respecting lines matching the game's
        real (word-blind) wrap engine, by padding intended line breaks so
        the engine's own wrap lands exactly there instead of mid-word.
        Also corrects for FORCED_WRAP_MEANINGS control codes embedded in
        this unit's script (set_flag_d10/line_center_calc/centered_text_setup
        -- see gcrts.control_position_risk), which force an unconditional
        engine-side line break independent of pixel budget. --center also
        centers every line's real content within the budget (like Word's
        center alignment) -- the engine otherwise always renders left-
        aligned from a fixed edge. Width defaults to gcrts.text_fitting's
        calibrated (safety-margined) estimate; override it while
        calibrating against the real game. Run 'resolve' BEFORE this, not
        after -- padding is computed against whatever characters are
        passed in, so fitting text that still has substitutable
        characters (e.g. "," before it becomes "、") computes padding for
        the wrong widths. See gcrts.text_fitting."""
        parts = arg.split()
        if not parts:
            print("usage: fit <id> [--pixel] [--center] [width_px]")
            return
        unit_id = parts[0]
        rest = parts[1:]
        use_pixel = "--pixel" in rest
        center = "--center" in rest
        rest = [p for p in rest if p not in ("--pixel", "--center")]
        width_px = int(rest[0]) if rest else None

        unit = self.state.get(unit_id)
        if unit is None:
            print(f"no such unit: {unit_id!r}")
            return

        from gcrts.font_workbench import classify_char
        from gcrts.text_fitting import fit_text_for_engine

        unresolved = [ch for ch in unit.edited_text if classify_char(ch) == "substitutable"]
        if unresolved:
            print(f"warning: {set(unresolved)} still need 'resolve' first -- fitting now would "
                  "compute padding against the wrong (pre-substitution) widths")

        atlas = None
        if use_pixel:
            from gcrts.glyph_atlas import GlyphAtlas

            atlas = GlyphAtlas.from_exe_file(r"c:/PCSXRedux/CAP0_full.bin")

        fitted = fit_text_for_engine(unit.edited_text, max_width_px=width_px, atlas=atlas, unit=unit, center=center)
        self.state.edit(unit.id, fitted)
        print(f"fitted: {fitted!r}")

    def do_check_layout(self, arg: str) -> None:
        """check_layout <id> [--pixel] -- run the full automatic layout/
        glyph check (missing glyph > control issue > boundary risk >
        pixel overflow > too many lines > awkward wrap > ok), storing the
        result as this unit's validation status. Pass --pixel to measure
        real glyph pixel widths (needs CAP0_full.bin) instead of the
        character-count fallback."""
        parts = arg.split()
        if not parts:
            print("usage: check_layout <id> [--pixel]")
            return
        unit_id = parts[0]
        use_pixel = "--pixel" in parts[1:]

        unit = self.state.get(unit_id)
        if unit is None:
            print(f"no such unit: {unit_id!r}")
            return

        from gcrts.layout_validation import check_layout

        atlas = None
        if use_pixel:
            from gcrts.glyph_atlas import GlyphAtlas

            atlas = GlyphAtlas.from_exe_file(r"c:/PCSXRedux/CAP0_full.bin")

        report = check_layout(unit, atlas=atlas)
        self.state.set_validation(unit.id, report.status.value, report.detail)
        print(f"{unit.id}: {report.status.value}")
        print(f"  detail: {report.detail}")
        print(f"  original_width_px={report.original_width_px} edited_width_px={report.edited_width_px} "
              f"estimated_lines={report.estimated_lines}")

    # --- Alternative Text Engine, Phase 3: CUSTOM_ENGINE layout plans --

    def do_layout_mode(self, arg: str) -> None:
        """layout_mode <id> <original|host_fitted|custom_engine> -- switch
        which rendering path this unit is marked to use. Does not itself
        change what gets injected today -- gcrts.live_injection still only
        ever performs HOST_FITTED-equivalent encoding; this records intent
        for when a CUSTOM_ENGINE consumer exists."""
        parts = arg.split()
        if len(parts) != 2:
            print("usage: layout_mode <id> <original|host_fitted|custom_engine>")
            return
        unit_id, mode_str = parts
        from gcrts.render_mode import RenderMode

        try:
            mode = RenderMode(mode_str.lower())
        except ValueError:
            print(f"unknown render mode: {mode_str!r} (expected one of: {', '.join(m.value for m in RenderMode)})")
            return
        try:
            self.state.set_render_mode(unit_id, mode)
        except KeyError:
            print(f"no such unit: {unit_id!r}")
            return
        print(f"{unit_id}: render_mode -> {mode.value}")

    def do_layout_auto(self, arg: str) -> None:
        """layout_auto <id> [--pixel] [width_px] -- build a starting
        CUSTOM_ENGINE layout plan from the unit's current edited_text,
        reusing gcrts.text_fitting's word-safe line grouping (see
        gcrts.layout_plan_builder). Switches the unit to CUSTOM_ENGINE mode
        and attaches the plan; use layout_show to inspect it and
        layout_update_line/layout_add_line/layout_remove_line to adjust it
        by hand afterward."""
        parts = arg.split()
        if not parts:
            print("usage: layout_auto <id> [--pixel] [width_px]")
            return
        unit_id = parts[0]
        rest = parts[1:]
        use_pixel = "--pixel" in rest
        rest = [p for p in rest if p != "--pixel"]
        width_px = int(rest[0]) if rest else None

        unit = self.state.get(unit_id)
        if unit is None:
            print(f"no such unit: {unit_id!r}")
            return

        from gcrts.layout_plan_builder import build_auto_layout_plan

        atlas = None
        if use_pixel:
            from gcrts.glyph_atlas import GlyphAtlas

            atlas = GlyphAtlas.from_exe_file(r"c:/PCSXRedux/CAP0_full.bin")

        plan = build_auto_layout_plan(unit, max_width_px=width_px, atlas=atlas)
        self.state.set_layout_plan(unit.id, plan)
        self.state.set_render_mode(unit.id, plan.render_mode)
        print(f"{unit.id}: built a {len(plan.lines)}-line CUSTOM_ENGINE plan")
        for i, line in enumerate(plan.lines):
            print(f"  [{i}] ({line.x},{line.y}) {line.alignment.value}: {line.text!r}")

    def do_layout_show(self, arg: str) -> None:
        """layout_show <id> -- print the unit's current layout plan, if any."""
        unit_id = arg.strip()
        if not unit_id:
            print("usage: layout_show <id>")
            return
        unit = self.state.get(unit_id)
        if unit is None:
            print(f"no such unit: {unit_id!r}")
            return
        plan = unit.layout_plan
        if plan is None:
            print(f"{unit_id}: no layout plan (render_mode={unit.render_mode.value})")
            return
        print(f"{unit_id}: render_mode={unit.render_mode.value} layout_mode={plan.layout_mode.value} "
              f"paragraph_end={plan.paragraph_end} page_transition={plan.page_transition.value}")
        for i, line in enumerate(plan.lines):
            print(f"  [{i}] ({line.x},{line.y}) {line.alignment.value} max_width_px={line.max_width_px}: {line.text!r}")

    def do_layout_add_line(self, arg: str) -> None:
        """layout_add_line <id> <x> <y> <left|center|right> <text...> --
        append a new line to the unit's layout plan (must already have one
        -- run layout_auto first). start/end_character_index are set to
        (0, len(text)) as a placeholder; they only matter once a plan is
        encoded via gcrts.layout_descriptor, which recomputes them from
        each line's actual text at that point, not from these fields."""
        parts = arg.split(" ", 4)
        if len(parts) < 5:
            print("usage: layout_add_line <id> <x> <y> <left|center|right> <text>")
            return
        unit_id, x_str, y_str, alignment_str, text = parts
        unit = self.state.get(unit_id)
        if unit is None:
            print(f"no such unit: {unit_id!r}")
            return
        if unit.layout_plan is None:
            print(f"{unit_id} has no layout plan yet -- run 'layout_auto {unit_id}' first")
            return

        from gcrts.editor_layout_plan import LayoutAlignment, LayoutLine

        try:
            alignment = LayoutAlignment(alignment_str.lower())
        except ValueError:
            print(f"unknown alignment: {alignment_str!r} (expected left|center|right)")
            return

        line = LayoutLine(
            text=text, start_character_index=0, end_character_index=len(text),
            x=int(x_str), y=int(y_str), alignment=alignment,
        )
        unit.layout_plan.add_line(line)
        print(f"{unit_id}: added line {len(unit.layout_plan.lines) - 1}: {text!r}")

    def do_layout_update_line(self, arg: str) -> None:
        """layout_update_line <id> <line_index> <x|y|align|text> <value...> --
        update one field of one line in the unit's layout plan."""
        parts = arg.split(" ", 3)
        if len(parts) < 4:
            print("usage: layout_update_line <id> <line_index> <x|y|align|text> <value>")
            return
        unit_id, index_str, field_name, value = parts
        unit = self.state.get(unit_id)
        if unit is None:
            print(f"no such unit: {unit_id!r}")
            return
        if unit.layout_plan is None:
            print(f"{unit_id} has no layout plan yet -- run 'layout_auto {unit_id}' first")
            return

        try:
            index = int(index_str)
        except ValueError:
            print(f"line index must be an integer, got {index_str!r}")
            return

        from gcrts.editor_layout_plan import LayoutAlignment

        kwargs: dict = {}
        if field_name == "x":
            kwargs["x"] = int(value)
        elif field_name == "y":
            kwargs["y"] = int(value)
        elif field_name == "text":
            kwargs["text"] = value
        elif field_name in ("align", "alignment"):
            try:
                kwargs["alignment"] = LayoutAlignment(value.lower())
            except ValueError:
                print(f"unknown alignment: {value!r} (expected left|center|right)")
                return
        else:
            print(f"unknown field: {field_name!r} (expected x|y|align|text)")
            return

        try:
            unit.layout_plan.update_line(index, **kwargs)
        except IndexError as e:
            print(str(e))
            return
        print(f"{unit_id}: line {index} updated ({field_name}={value!r})")

    def do_layout_remove_line(self, arg: str) -> None:
        """layout_remove_line <id> <line_index> -- remove one line from the
        unit's layout plan."""
        parts = arg.split()
        if len(parts) != 2:
            print("usage: layout_remove_line <id> <line_index>")
            return
        unit_id, index_str = parts
        unit = self.state.get(unit_id)
        if unit is None:
            print(f"no such unit: {unit_id!r}")
            return
        if unit.layout_plan is None:
            print(f"{unit_id} has no layout plan yet -- run 'layout_auto {unit_id}' first")
            return
        try:
            index = int(index_str)
            unit.layout_plan.remove_line(index)
        except (ValueError, IndexError) as e:
            print(str(e))
            return
        print(f"{unit_id}: removed line {index}")

    def do_layout_preview(self, arg: str) -> None:
        """layout_preview <id> [--pixel] -- compute (not render) a
        LayoutPreview for the unit's current layout plan: measured pixel
        width per line, which lines overflow their own budget, whether the
        plan exceeds the confirmed MAX_VISIBLE_LINES=4, and any characters
        with no known glyph. This is data only -- gcrts.layout_preview
        does no drawing; a real software-rendered preview is later scope."""
        parts = arg.split()
        if not parts:
            print("usage: layout_preview <id> [--pixel]")
            return
        unit_id = parts[0]
        use_pixel = "--pixel" in parts[1:]

        unit = self.state.get(unit_id)
        if unit is None:
            print(f"no such unit: {unit_id!r}")
            return
        if unit.layout_plan is None:
            print(f"{unit_id} has no layout plan yet -- run 'layout_auto {unit_id}' first")
            return

        from gcrts.layout_preview import build_preview

        atlas = None
        if use_pixel:
            from gcrts.glyph_atlas import GlyphAtlas

            atlas = GlyphAtlas.from_exe_file(r"c:/PCSXRedux/CAP0_full.bin")

        preview = build_preview(unit.layout_plan, atlas=atlas)
        print(f"{unit_id}: fits={preview.fits} too_many_lines={preview.too_many_lines}")
        for line in preview.lines:
            flag = " OVERFLOW" if line.overflows else ""
            print(f"  [{line.index}] {line.measured_width_px}/{line.budget_px}px{flag}: {line.text!r}")
        if preview.missing_glyphs:
            print(f"  missing glyphs: {preview.missing_glyphs}")

    def do_layout_render(self, arg: str) -> None:
        """layout_render <id> <output_path.png> -- render (gcrts.layout_software_preview)
        the unit's current layout plan into a real PNG using the actual
        glyph atlas, showing textbox bounds, baseline, overflow (red
        outline), and missing glyphs (red box) -- a fast validation layer,
        not a substitute for watching the actual emulator render it.

        KNOWN LIMITATION: this project has never captured the live,
        per-chapter glyph-bitmap resource blob gcrts.glyph_atlas.GlyphAtlas
        needs to decode a REAL glyph's pixels (see that module's own
        docstring) -- only the static EXE-embedded width table is loaded
        here, matching every other --pixel command in this file. Without
        that blob, every character will render as a missing-glyph marker,
        which is the honest result, not a silent fallback pretending to
        show real glyph shapes it doesn't have."""
        parts = arg.split()
        if len(parts) != 2:
            print("usage: layout_render <id> <output_path.png>")
            return
        unit_id, output_path = parts

        unit = self.state.get(unit_id)
        if unit is None:
            print(f"no such unit: {unit_id!r}")
            return
        if unit.layout_plan is None:
            print(f"{unit_id} has no layout plan yet -- run 'layout_auto {unit_id}' first")
            return

        from gcrts.glyph_atlas import GlyphAtlas
        from gcrts.layout_software_preview import render_layout_plan_to_file

        atlas = GlyphAtlas.from_exe_file(r"c:/PCSXRedux/CAP0_full.bin")
        render_layout_plan_to_file(unit.layout_plan, atlas, output_path)
        print(f"{unit_id}: rendered to {output_path}")

    def do_flag_style(self, arg: str) -> None:
        """flag_style <id> [note...] -- manually mark a unit as needing a
        style/naturalness review (never auto-detected -- see
        gcrts.layout_validation's module docstring)."""
        parts = arg.split(" ", 1)
        if not parts or not parts[0]:
            print("usage: flag_style <id> [note]")
            return
        unit_id = parts[0]
        note = parts[1] if len(parts) > 1 else ""
        try:
            self.state.set_validation(unit_id, "style_review_needed", note)
        except KeyError:
            print(f"no such unit: {unit_id!r}")
            return
        print(f"{unit_id} flagged for style review")

    def do_filter(self, arg: str) -> None:
        """filter modified|missing|status:<value>|type:<value>|validation:<value> -- quick filters."""
        arg = arg.strip()
        kwargs: dict = {}
        if arg == "modified":
            kwargs["modified_only"] = True
        elif arg == "missing":
            kwargs["missing_glyphs_only"] = True
        elif arg.startswith("status:"):
            kwargs["status"] = UnitStatus(arg.split(":", 1)[1])
        elif arg.startswith("type:"):
            kwargs["text_type"] = arg.split(":", 1)[1]
        elif arg.startswith("validation:"):
            kwargs["validation_status"] = arg.split(":", 1)[1]
        else:
            print("usage: filter modified|missing|status:<value>|type:<value>|validation:<value>")
            return
        for u in self.state.search(**kwargs):
            print(f"{u.id:24} [{self.state.status(u.id).value:10}] {_preview(u.edited_text)!r}")

    # --- editing --------------------------------------------------------

    def do_edit(self, arg: str) -> None:
        """edit <id> <new text> -- set a unit's edited_text."""
        parts = arg.split(" ", 1)
        if len(parts) < 2:
            print("usage: edit <id> <new text>")
            return
        unit_id, new_text = parts
        try:
            self.state.edit(unit_id, new_text)
        except KeyError:
            print(f"no such unit: {unit_id!r}")
            return
        print(f"{unit_id} -> status now {self.state.status(unit_id).value}")

    def do_reset(self, arg: str) -> None:
        """reset <id> -- revert edited_text back to original_text."""
        unit_id = arg.strip()
        try:
            self.state.reset(unit_id)
        except KeyError:
            print(f"no such unit: {unit_id!r}")
            return
        print(f"{unit_id} reset to original")

    do_revert = do_reset  # spec's preferred term for the same operation

    def do_note(self, arg: str) -> None:
        """note <id> <text> -- attach a researcher/translator comment."""
        parts = arg.split(" ", 1)
        if len(parts) < 2:
            print("usage: note <id> <text>")
            return
        unit_id, text = parts
        try:
            self.state.note(unit_id, text)
        except KeyError:
            print(f"no such unit: {unit_id!r}")
            return
        print(f"note saved for {unit_id}")

    # --- extraction / session persistence --------------------------------

    def do_extract(self, arg: str) -> None:
        """extract <scene_id> [host] [port] -- capture the live script buffer."""
        parts = arg.split()
        if not parts:
            print("usage: extract <scene_id> [host] [port]")
            return
        scene_id = parts[0]
        host = parts[1] if len(parts) > 1 else "127.0.0.1"
        port = int(parts[2]) if len(parts) > 2 else 3333
        from gcrts.script_unit import extract_live_script_units

        try:
            units = extract_live_script_units(scene_id, host=host, port=port)
        except OSError as e:
            print(f"extraction failed: {e}")
            return
        self.state.load_units(units)
        print(f"loaded {len(units)} units from live RAM")

    def do_validate(self, arg: str) -> None:
        """validate <id> -- run automatic checks (missing glyphs, control-code
        preservation). Does NOT confirm fit/overflow -- that needs 'confirm'
        after watching the line render in-game."""
        unit = self.state.get(arg.strip())
        if unit is None:
            print(f"no such unit: {arg!r}")
            return
        from gcrts.validation import auto_validate

        report = auto_validate(unit)
        self.state.set_validation(unit.id, report.status.value, report.detail)
        print(f"{unit.id}: {report.status.value} -- {report.detail}")

    def do_confirm(self, arg: str) -> None:
        """confirm <id> ok|overflow [note...] -- operator-entered result
        after watching the injected line render in-game."""
        parts = arg.split(" ", 2)
        if len(parts) < 2 or parts[1] not in ("ok", "overflow"):
            print("usage: confirm <id> ok|overflow [note]")
            return
        unit_id, status = parts[0], parts[1]
        note = parts[2] if len(parts) > 2 else ""
        try:
            self.state.set_validation(unit_id, status, note)
        except KeyError:
            print(f"no such unit: {unit_id!r}")
            return
        print(f"{unit_id} confirmed as {status}")

    def do_glyphs(self, arg: str) -> None:
        """glyphs -- list all currently mapped character codes and how many there are."""
        from gcrts.font_workbench import list_mapped_glyphs

        mapped = list_mapped_glyphs()
        print(f"{len(mapped)} codes mapped")
        for code in sorted(mapped):
            print(f"  {code:#06x}: {mapped[code]!r}")

    def do_audit(self, arg: str) -> None:
        """audit <id> -- preview glyph coverage for a unit's edited_text
        (mapped / substitutable / unmapped per character), no changes made."""
        unit = self.state.get(arg.strip())
        if unit is None:
            print(f"no such unit: {arg!r}")
            return
        from gcrts.font_workbench import audit_text

        for entry in audit_text(unit.edited_text):
            extra = f" -> {entry['substitute']!r}" if "substitute" in entry else ""
            print(f"  {entry['char']!r:6} {entry['classification']}{extra}")

    def do_resolve(self, arg: str) -> None:
        """resolve <id> [host] [port] -- apply known substitutions and
        auto-inject brand-new glyphs (live, into an unused per-scene slot)
        for any characters in the unit's edited_text that are still
        unmapped, then update edited_text to the resolved version."""
        parts = arg.split()
        if not parts:
            print("usage: resolve <id> [host] [port]")
            return
        unit_id = parts[0]
        host = parts[1] if len(parts) > 1 else "127.0.0.1"
        port = int(parts[2]) if len(parts) > 2 else 3333

        unit = self.state.get(unit_id)
        if unit is None:
            print(f"no such unit: {unit_id!r}")
            return

        from gcrts.font_extension import DEFAULT_FONT_PATH
        from gcrts.font_workbench import auto_resolve_missing_glyphs
        from gcrts.glyph_atlas import GlyphAtlas
        from gcrts.live_extract import GdbClient

        atlas = GlyphAtlas.from_exe_file(r"c:/PCSXRedux/CAP0_full.bin")
        try:
            client = GdbClient(host=host, port=port)
        except OSError as e:
            print(f"could not connect for live injection: {e}")
            return

        report = auto_resolve_missing_glyphs(unit.edited_text, atlas, client, self.glyph_log)
        client.close()

        for entry in report.injected:
            print(f"injected new glyph {entry.char!r} at code {entry.code:#06x}")
        if report.unresolved:
            print(f"unresolved (no free slot / not attempted): {report.unresolved}")
        self.state.edit(unit.id, report.resolved_text)
        print(f"edited_text updated to: {report.resolved_text!r}")

    def do_glyphlog(self, arg: str) -> None:
        """glyphlog [save <path>] -- show (or save) the log of glyphs
        injected this session, including the palette values used."""
        parts = arg.split(" ", 1)
        if parts and parts[0] == "save" and len(parts) > 1:
            self.glyph_log.save(parts[1])
            print(f"glyph log saved to {parts[1]}")
            return
        if not self.glyph_log.entries:
            print("(no glyphs injected this session)")
            return
        for e in self.glyph_log.entries:
            print(f"  {e.code:#06x} {e.char!r} bg={e.background_value} ink={e.ink_value} font={e.font_path} note={e.note!r}")

    def do_inject_unit(self, arg: str) -> None:
        """inject_unit <id> [--pixel] [host] [port] -- the guarded,
        single-unit workflow: validates this unit (missing glyph, control
        preservation, boundary, layout) first. Hard-blocks on missing_glyph
        or control_issue without ever touching the network; warns but
        proceeds on pixel_overflow/too_many_lines/awkward_wrap/
        boundary_risk. Always injects the WHOLE buffer under the hood (see
        gcrts.guarded_injection's docstring for why), logging every
        attempt to this unit's injection history either way."""
        parts = arg.split()
        if not parts:
            print("usage: inject_unit <id> [--pixel] [host] [port]")
            return
        unit_id = parts[0]
        rest = parts[1:]
        use_pixel = "--pixel" in rest
        rest = [p for p in rest if p != "--pixel"]
        host = rest[0] if len(rest) > 0 else "127.0.0.1"
        port = int(rest[1]) if len(rest) > 1 else 3333

        from gcrts.guarded_injection import inject_unit_guarded

        atlas = None
        if use_pixel:
            from gcrts.glyph_atlas import GlyphAtlas

            atlas = GlyphAtlas.from_exe_file(r"c:/PCSXRedux/CAP0_full.bin")

        try:
            result = inject_unit_guarded(self.state, unit_id, atlas=atlas, host=host, port=port)
        except KeyError:
            print(f"no such unit: {unit_id!r}")
            return

        print(f"layout status: {result.layout_status} -- {result.layout_detail}")
        if not result.proceeded:
            print(f"BLOCKED: {result.blocked_reason}")
            return
        for w in result.injection.warnings:
            print(f"warning: {w}")
        if result.injection.success:
            print(f"injected {result.injection.bytes_written} bytes successfully")
        else:
            print(f"injection FAILED: {result.injection.error}")

    def do_history(self, arg: str) -> None:
        """history <id> -- show this unit's injection attempt history."""
        unit_id = arg.strip()
        if self.state.get(unit_id) is None:
            print(f"no such unit: {unit_id!r}")
            return
        history = self.state.injection_history(unit_id)
        if not history:
            print("(no injection attempts recorded for this unit yet)")
            return
        for e in history:
            outcome = "OK" if e["success"] else "FAILED"
            print(f"  {e['timestamp']} [{outcome}] bytes={e['bytes_written']} error={e['error']!r}")

    def do_inject(self, arg: str) -> None:
        """inject [host] [port] -- re-encode and write all loaded units
        back into live RAM (all units must share one buffer -- true for
        anything loaded via 'extract'). Safe to run repeatedly."""
        if not self.state.units:
            print("no units loaded -- try 'extract <scene_id>' first")
            return
        parts = arg.split()
        host = parts[0] if len(parts) > 0 else "127.0.0.1"
        port = int(parts[1]) if len(parts) > 1 else 3333

        from gcrts.live_injection import inject_all_live

        result = inject_all_live(self.state, host=host, port=port)
        for w in result.warnings:
            print(f"warning: {w}")
        if result.success:
            print(f"injected {result.bytes_written} bytes successfully")
        else:
            print(f"injection FAILED: {result.error}")

    def do_types(self, arg: str) -> None:
        """types -- show which text-type render paths are actually
        implemented versus still-unresearched stubs."""
        from gcrts.render_paths import coverage_report

        for row in coverage_report():
            state = "implemented" if row["implemented"] else "NOT IMPLEMENTED"
            print(f"  {row['text_type']:16} {state}")
            if "notes" in row:
                print(f"    notes: {row['notes']}")

    def do_extract_type(self, arg: str) -> None:
        """extract_type <text_type> <scene_id> [host] [port] -- capture via
        a specific render-path adapter (see 'types' for what's actually
        implemented; unimplemented ones raise a clear research-needed error
        rather than silently returning nothing)."""
        parts = arg.split()
        if len(parts) < 2:
            print("usage: extract_type <text_type> <scene_id> [host] [port]")
            return
        text_type, scene_id = parts[0], parts[1]
        host = parts[2] if len(parts) > 2 else "127.0.0.1"
        port = int(parts[3]) if len(parts) > 3 else 3333

        from gcrts.render_paths import extract_units_for

        try:
            units = extract_units_for(text_type, scene_id, host=host, port=port)
        except KeyError as e:
            print(str(e))
            return
        except NotImplementedError as e:
            print(str(e))
            return
        except OSError as e:
            print(f"extraction failed: {e}")
            return
        self.state.load_units(units)
        print(f"loaded {len(units)} units (text_type={text_type!r})")

    def do_save(self, arg: str) -> None:
        """save <path> -- save the current session as JSON."""
        path = arg.strip()
        if not path:
            print("usage: save <path>")
            return
        self.state.save_session(path)
        print(f"session saved to {path}")

    def do_load(self, arg: str) -> None:
        """load <path> -- load a previously saved session."""
        path = arg.strip()
        if not path:
            print("usage: load <path>")
            return
        self.state = EditorState.load_session(path)
        print(f"loaded {len(self.state.units)} units from {path}")

    # --- misc -----------------------------------------------------------

    def do_quit(self, arg: str) -> bool:
        """quit -- exit the editor."""
        return True

    do_exit = do_quit
    do_EOF = do_quit


def main() -> None:
    parser = argparse.ArgumentParser(description="Live Text Workbench terminal editor")
    parser.add_argument("--extract", help="scene id to extract from live RAM on startup")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3333)
    args = parser.parse_args()

    cli = EditorCLI()
    if args.extract:
        cli.onecmd(f"extract {args.extract} {args.host} {args.port}")
    cli.cmdloop()


if __name__ == "__main__":
    main()
