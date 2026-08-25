"""Tests for gcrts.evidence_bundle -- pure serialization, no GUI/emulator."""
from __future__ import annotations

from gcrts.evidence_bundle import EvidenceBundle, OverlayBackend, ValidationResult


def _sample() -> EvidenceBundle:
    return EvidenceBundle(
        scenario_name="generic_gameplay_sentence",
        timestamp="2026-08-25T12:00:00Z",
        backend=OverlayBackend.EXTERNAL_HOST,
        result=ValidationResult.PASS,
        runtime_context={"executable_id": "CAP0.EXE", "mode": "GAMEPLAY"},
        host_screenshot_path="evidence/host_001.png",
        emulator_screenshot_path="evidence/emu_001.png",
        event_log=["overlay shown", "screenshot captured", "overlay hidden"],
        notes="smoke test",
    )


def test_round_trip_through_dict():
    bundle = _sample()
    restored = EvidenceBundle.from_dict(bundle.to_dict())
    assert restored == bundle


def test_round_trip_through_file(tmp_path):
    bundle = _sample()
    path = tmp_path / "evidence.json"
    bundle.save(str(path))
    restored = EvidenceBundle.load(str(path))
    assert restored == bundle


def test_unsupported_result_is_distinct_from_fail():
    bundle = _sample()
    bundle.result = ValidationResult.UNSUPPORTED
    d = bundle.to_dict()
    assert d["result"] == "UNSUPPORTED"
    assert d["result"] != ValidationResult.FAIL.value


def test_backend_marker_distinguishes_external_from_internal():
    external = _sample()
    internal = _sample()
    internal.backend = OverlayBackend.INTERNAL_PS1
    assert external.to_dict()["backend"] != internal.to_dict()["backend"]
