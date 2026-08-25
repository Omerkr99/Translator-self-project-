"""Tests for gcrts.evidence -- the shared confidence/evidence model."""
from __future__ import annotations

import pytest

from gcrts.evidence import Claim, Confidence, Evidence, is_stronger


def test_confirmed_live_is_stronger_than_static_code_match():
    assert is_stronger(Confidence.CONFIRMED_LIVE, Confidence.STATIC_CODE_MATCH)
    assert not is_stronger(Confidence.STATIC_CODE_MATCH, Confidence.CONFIRMED_LIVE)


def test_unknown_is_weaker_than_hypothesis():
    assert is_stronger(Confidence.HYPOTHESIS, Confidence.UNKNOWN)


def test_disproven_is_not_rank_comparable():
    with pytest.raises(ValueError):
        is_stronger(Confidence.DISPROVEN, Confidence.CONFIRMED_LIVE)
    with pytest.raises(ValueError):
        is_stronger(Confidence.HYPOTHESIS, Confidence.DISPROVEN)


def test_evidence_round_trips_through_dict():
    ev = Evidence(kind="GDB_BREAKPOINT", detail={"address": "0x8006E5E4", "register": "$a1", "value": 8})
    restored = Evidence.from_dict(ev.to_dict())
    assert restored == ev


def test_claim_round_trips_with_multiple_evidence_items():
    claim = Claim(
        claim="CAP0.EXE callsite loads MPRO.EXE",
        confidence=Confidence.CONFIRMED_LIVE,
        evidence=[
            Evidence(kind="STATIC_CODE", detail={"address": "0x8006CCB0"}),
            Evidence(kind="GDB_BREAKPOINT", detail={"register": "$a1", "value": 8}),
        ],
    )
    restored = Claim.from_dict(claim.to_dict())
    assert restored.claim == claim.claim
    assert restored.confidence == Confidence.CONFIRMED_LIVE
    assert len(restored.evidence) == 2


def test_add_evidence_can_upgrade_confidence():
    claim = Claim(claim="MPRO.EXE plays PRO.STR", confidence=Confidence.STATIC_CODE_MATCH)
    claim.add_evidence(Evidence(kind="GDB_BREAKPOINT", detail={"value": 8}), new_confidence=Confidence.CONFIRMED_LIVE)
    assert claim.confidence == Confidence.CONFIRMED_LIVE
    assert len(claim.evidence) == 1


def test_add_evidence_can_record_a_disproven_correction():
    claim = Claim(claim="CAP0.EXE hands off to CAPX.EXE", confidence=Confidence.HYPOTHESIS)
    claim.add_evidence(
        Evidence(kind="GDB_BREAKPOINT", detail={"result": "never fired"}, note="disproven live"),
        new_confidence=Confidence.DISPROVEN,
    )
    assert claim.confidence == Confidence.DISPROVEN
