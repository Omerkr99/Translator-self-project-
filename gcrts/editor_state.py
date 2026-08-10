"""Live Text Workbench, Phase 2: the editor's backend state model.

Deliberately separated from any UI/renderer (per the workbench's
"editor state model separated from renderer/injector logic"
requirement): this module only holds ScriptUnits plus per-unit workflow
status and notes, and exposes search/filter/edit operations. A terminal
UI (gcrts/editor_cli.py) sits on top of this; a future desktop UI could
sit on the exact same class with zero changes here. Live injection
(Phase 3) and validation (Phase 4) will each add their own layer on top
of this state rather than being folded into it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from gcrts.editor_layout_plan import EditorLayoutPlan
from gcrts.render_mode import RenderMode
from gcrts.script_unit import ScriptUnit

# Bumped to 2 when the Alternative Text Engine's Phase 1 fields
# (render_mode, layout_plan, runtime_patch_status, preview_status) were
# added to ScriptUnit. There is no structural migration to perform between
# version 1 and 2 -- ScriptUnit.from_dict()'s own per-field .get() defaults
# already make an unversioned (pre-version-field) session load correctly,
# with every unit defaulting to HOST_FITTED and no layout plan. This
# constant exists so a FUTURE version that DOES need a real migration step
# has something to branch on, and so a saved session records what it was
# written by.
CURRENT_SCHEMA_VERSION = 2


class UnitStatus(Enum):
    UNMODIFIED = "unmodified"
    MODIFIED = "modified"
    INJECTED = "injected"
    INVALID = "invalid"


@dataclass
class EditorState:
    """Note: validation status (gcrts.validation.ValidationStatus) is
    stored here as plain (status_value, detail) string tuples rather than
    importing gcrts.validation's types directly -- gcrts.validation
    imports gcrts.live_injection, which imports this module, so importing
    ValidationStatus here would create a circular import. Keeping this
    module's storage untyped-but-generic avoids that; callers pass/read
    `.value` strings."""

    units: list[ScriptUnit] = field(default_factory=list)
    _status: dict[str, UnitStatus] = field(default_factory=dict)
    _notes: dict[str, str] = field(default_factory=dict)
    _validation: dict[str, tuple[str, str]] = field(default_factory=dict)
    _injection_log: list[dict] = field(default_factory=list)

    def load_units(self, units: list[ScriptUnit]) -> None:
        """Add units to the session, defaulting new ones to UNMODIFIED.
        Existing status/notes for an id already in the session are kept."""
        self.units = units
        for u in units:
            self._status.setdefault(u.id, UnitStatus.MODIFIED if u.is_modified else UnitStatus.UNMODIFIED)

    def get(self, unit_id: str) -> ScriptUnit | None:
        return next((u for u in self.units if u.id == unit_id), None)

    def status(self, unit_id: str) -> UnitStatus:
        return self._status.get(unit_id, UnitStatus.UNMODIFIED)

    def set_status(self, unit_id: str, status: UnitStatus) -> None:
        if self.get(unit_id) is None:
            raise KeyError(unit_id)
        self._status[unit_id] = status

    def edit(self, unit_id: str, new_text: str) -> None:
        """Set a unit's edited_text and update its status accordingly.
        Does NOT touch raw_codes/control_events -- re-encoding those from
        edited_text is Phase 3's job (gcrts.script_encoder already exists
        for this at the ScriptSegment level)."""
        unit = self.get(unit_id)
        if unit is None:
            raise KeyError(unit_id)
        unit.edited_text = new_text
        if self.status(unit_id) != UnitStatus.INJECTED:
            self._status[unit_id] = UnitStatus.MODIFIED if unit.is_modified else UnitStatus.UNMODIFIED

    def reset(self, unit_id: str) -> None:
        """Revert edited_text back to original_text."""
        unit = self.get(unit_id)
        if unit is None:
            raise KeyError(unit_id)
        self.edit(unit_id, unit.original_text)

    # --- Alternative Text Engine, Phase 3: render mode + layout plan ---

    def set_render_mode(self, unit_id: str, mode: RenderMode) -> None:
        unit = self.get(unit_id)
        if unit is None:
            raise KeyError(unit_id)
        unit.render_mode = mode

    def get_layout_plan(self, unit_id: str) -> EditorLayoutPlan | None:
        unit = self.get(unit_id)
        if unit is None:
            raise KeyError(unit_id)
        return unit.layout_plan

    def set_layout_plan(self, unit_id: str, plan: EditorLayoutPlan | None) -> None:
        """Attach (or clear, if `plan` is None) a layout plan to a unit.
        Does NOT change render_mode -- an operator may want to draft/edit a
        CUSTOM_ENGINE plan while still rendering HOST_FITTED live, exactly
        like the master prompt's fallback requirement expects (a plan that
        fails validation should be able to fall back without losing the
        draft that failed)."""
        unit = self.get(unit_id)
        if unit is None:
            raise KeyError(unit_id)
        unit.layout_plan = plan

    def validation_status(self, unit_id: str) -> str:
        return self._validation.get(unit_id, ("unknown", ""))[0]

    def validation_detail(self, unit_id: str) -> str:
        return self._validation.get(unit_id, ("unknown", ""))[1]

    def set_validation(self, unit_id: str, status_value: str, detail: str = "") -> None:
        if self.get(unit_id) is None:
            raise KeyError(unit_id)
        self._validation[unit_id] = (status_value, detail)

    def note(self, unit_id: str, text: str) -> None:
        if self.get(unit_id) is None:
            raise KeyError(unit_id)
        self._notes[unit_id] = text

    def get_note(self, unit_id: str) -> str:
        return self._notes.get(unit_id, "")

    def record_injection(self, unit_id: str, success: bool, bytes_written: int, error: str = "") -> None:
        """Append one entry to this session's injection history -- never
        overwrites or replaces previous entries for the same unit, so
        'injection history per unit' means the full sequence of attempts,
        not just the most recent one."""
        self._injection_log.append(
            {
                "unit_id": unit_id,
                "success": success,
                "bytes_written": bytes_written,
                "error": error,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    def injection_history(self, unit_id: str) -> list[dict]:
        return [e for e in self._injection_log if e["unit_id"] == unit_id]

    def all_injection_history(self) -> list[dict]:
        return list(self._injection_log)

    def search(
        self,
        query: str = "",
        text_type: str | None = None,
        status: UnitStatus | None = None,
        modified_only: bool = False,
        missing_glyphs_only: bool = False,
        validation_status: str | None = None,
    ) -> list[ScriptUnit]:
        results = self.units
        if query:
            q = query.lower()
            results = [
                u for u in results
                if q in u.id.lower() or q in u.original_text.lower() or q in u.edited_text.lower()
            ]
        if text_type is not None:
            results = [u for u in results if u.text_type == text_type]
        if status is not None:
            results = [u for u in results if self.status(u.id) == status]
        if modified_only:
            results = [u for u in results if u.is_modified]
        if missing_glyphs_only:
            results = [u for u in results if u.missing_glyphs]
        if validation_status is not None:
            results = [u for u in results if self.validation_status(u.id) == validation_status]
        return results

    def to_session_dict(self) -> dict:
        return {
            "schema_version": CURRENT_SCHEMA_VERSION,
            "units": [u.to_dict() for u in self.units],
            "status": {uid: s.value for uid, s in self._status.items()},
            "notes": dict(self._notes),
            "validation": {uid: {"status": v[0], "detail": v[1]} for uid, v in self._validation.items()},
            "injection_log": list(self._injection_log),
        }

    def save_session(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_session_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load_session(cls, path: str) -> "EditorState":
        """A missing `schema_version` key (any session saved before this
        field existed) is treated as version 1 -- ScriptUnit.from_dict's
        own field-level defaults make that load correctly with no separate
        migration step needed (see CURRENT_SCHEMA_VERSION's docstring)."""
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        d.setdefault("schema_version", 1)
        state = cls()
        state.units = [ScriptUnit.from_dict(u) for u in d["units"]]
        state._status = {uid: UnitStatus(v) for uid, v in d["status"].items()}
        state._notes = dict(d["notes"])
        state._validation = {
            uid: (v["status"], v["detail"]) for uid, v in d.get("validation", {}).items()
        }
        state._injection_log = list(d.get("injection_log", []))
        return state
