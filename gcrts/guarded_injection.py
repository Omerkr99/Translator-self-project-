"""Live Text Editor Workbench, Phase 5: guarded per-unit live injection.

Ties together everything built in earlier phases into the single safe
operator workflow this phase's spec asks for: select one unit, validate
it (missing glyph / control preservation / boundary / layout -- all via
gcrts.layout_validation.check_layout, which itself composes
gcrts.validation and gcrts.boundary_validation without duplicating
them), and only then call the EXISTING, unmodified
gcrts.live_injection.inject_all_live.

Why this always injects the WHOLE buffer, never just one unit's bytes
at its own fixed offset, even though the operator only edited one unit:
gcrts.live_injection's own docstring explains why patching in place is
unsafe the moment an edit changes length -- every unit after the edited
one would land at the wrong offset relative to what the reader expects.
"Inject only that unit" (this phase's own wording) means making it FEEL
like a single-unit operation from the operator's side; under the hood
it's still the same safe whole-buffer rewrite, with every OTHER unit's
text byte-identical to what it already was (gcrts.script_encoder's
untouched-segment shortcut guarantees that automatically).

HARD BLOCK (refuses to inject): missing_glyph, control_issue -- these
mean the encode would either fail outright or has already been shown to
change something it must not.
WARN BUT PROCEED: pixel_overflow, too_many_lines, awkward_wrap,
boundary_risk -- judgment calls an operator might reasonably override,
since the layout budget is an approximation, not a verified game limit.

Every attempt -- blocked or not, successful or not -- is logged via
gcrts.editor_state.EditorState.record_injection(), giving the "log each
live injection action" / "injection history per unit" the spec asks for.
"""
from __future__ import annotations

from dataclasses import dataclass

from gcrts.editor_state import EditorState
from gcrts.layout_validation import LayoutValidationStatus, check_layout
from gcrts.live_injection import InjectionResult, inject_all_live

BLOCKING_STATUSES = {LayoutValidationStatus.MISSING_GLYPH, LayoutValidationStatus.CONTROL_ISSUE}


@dataclass
class GuardedInjectionResult:
    unit_id: str
    proceeded: bool  # False if blocked before ever touching the network
    layout_status: str
    layout_detail: str
    blocked_reason: str = ""
    injection: InjectionResult | None = None  # None if blocked


def inject_unit_guarded(
    state: EditorState,
    unit_id: str,
    atlas=None,
    host: str = "127.0.0.1",
    port: int = 3333,
) -> GuardedInjectionResult:
    """Validate `unit_id`'s current edited_text, then -- unless blocked --
    inject the whole buffer it belongs to. Always records the attempt in
    `state`'s injection history, whether it proceeded or not."""
    unit = state.get(unit_id)
    if unit is None:
        raise KeyError(unit_id)

    report = check_layout(unit, atlas=atlas)
    state.set_validation(unit.id, report.status.value, report.detail)

    if report.status in BLOCKING_STATUSES:
        state.record_injection(unit_id, success=False, bytes_written=0, error=f"blocked: {report.status.value}")
        return GuardedInjectionResult(
            unit_id=unit_id,
            proceeded=False,
            layout_status=report.status.value,
            layout_detail=report.detail,
            blocked_reason=f"{report.status.value}: {report.detail}",
        )

    result = inject_all_live(state, host=host, port=port)
    state.record_injection(unit_id, success=result.success, bytes_written=result.bytes_written, error=result.error or "")
    return GuardedInjectionResult(
        unit_id=unit_id,
        proceeded=True,
        layout_status=report.status.value,
        layout_detail=report.detail,
        injection=result,
    )
