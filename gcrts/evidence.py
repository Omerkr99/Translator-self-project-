"""Shared confidence/evidence model for claims made anywhere in this
project -- movie mappings, audio identification, runtime context
resolution, patch profiles, and (going forward) the overlay engine's
own runtime-context resolver.

Before this module, every domain independently invented its own
similar-but-not-identical confidence enum (`gcrts.movie_detection
.MovieMatchConfidence`, `gcrts.semantic_label_store.VerificationSource`,
`gcrts.mips_patch_profile.PatchProfileStatus`, and more) -- consistent
in spirit, never in implementation. The toolkit-readiness audit
(`docs/status/TOOLKIT_READINESS_AUDIT.md` §16/§24) flagged this as a
toolkit-design unknown worth a small, additive fix, not a rewrite:
this module defines one shared `Confidence` tier set and an
`Evidence`/`Claim` pair, adopted incrementally by whichever module
wants it -- existing domain-specific enums are NOT required to migrate,
and nothing here changes their behavior.

Tiers mirror what this project has actually used in practice, gathered
across every investigation this session touched:

- `CONFIRMED_LIVE` -- witnessed directly (a GDB breakpoint fired with
  an expected value, a human listened and confirmed an audio match, a
  live console-text capture named an exact file).
- `STATIC_CODE_MATCH` -- disassembly or static analysis of real
  executable bytes proves a specific fact, but it has not been
  witnessed happening live.
- `RUNTIME_DERIVED` -- a live runtime observation supports a
  conclusion, but through inference (e.g. a correlation) rather than a
  single decisive witnessed event.
- `TEST_VALIDATED` -- an automated test (synthetic or real-data)
  passes and is the only evidence backing the claim.
- `INFERRED` -- reasonably concluded from other confirmed facts, not
  independently checked itself.
- `HYPOTHESIS` -- a proposed explanation, not yet checked.
- `UNKNOWN` -- no evidence either way; a valid, honest state, not a
  placeholder for "probably true."
- `DISPROVEN` -- was previously believed (at some confidence tier) and
  has since been directly contradicted by real evidence. Per this
  project's own standing rule, a disproven claim is corrected in place,
  never quietly deleted -- keeping the `DISPROVEN` record is itself
  useful (see the `CAP0.EXE`-hands-off-to-`CAPX.EXE` case in
  `docs/renderer/MOVIE_LOADER_ARCHITECTURE.md`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Confidence(str, Enum):
    CONFIRMED_LIVE = "CONFIRMED_LIVE"
    STATIC_CODE_MATCH = "STATIC_CODE_MATCH"
    RUNTIME_DERIVED = "RUNTIME_DERIVED"
    TEST_VALIDATED = "TEST_VALIDATED"
    INFERRED = "INFERRED"
    HYPOTHESIS = "HYPOTHESIS"
    UNKNOWN = "UNKNOWN"
    DISPROVEN = "DISPROVEN"


# A partial order a caller can use to compare two tiers when deciding
# whether new evidence should upgrade an existing claim (e.g. never
# silently downgrade a CONFIRMED_LIVE claim just because a later,
# weaker check ran). DISPROVEN is intentionally not comparable to the
# others by rank -- it isn't "worse evidence," it's a correction, and
# should always be handled explicitly rather than by rank comparison.
_RANK: dict[Confidence, int] = {
    Confidence.UNKNOWN: 0,
    Confidence.HYPOTHESIS: 1,
    Confidence.INFERRED: 2,
    Confidence.TEST_VALIDATED: 3,
    Confidence.RUNTIME_DERIVED: 4,
    Confidence.STATIC_CODE_MATCH: 5,
    Confidence.CONFIRMED_LIVE: 6,
}


def is_stronger(a: Confidence, b: Confidence) -> bool:
    """True if `a` is strictly stronger evidence than `b`. Raises
    ValueError if either tier is DISPROVEN -- that comparison is never
    meaningful by rank, callers must handle it explicitly."""
    if a == Confidence.DISPROVEN or b == Confidence.DISPROVEN:
        raise ValueError("DISPROVEN is not rank-comparable; handle it explicitly")
    return _RANK[a] > _RANK[b]


@dataclass(frozen=True)
class Evidence:
    """One concrete, reproducible piece of support for a claim. `kind`
    is a short free-text tag (e.g. "STATIC_CODE", "GDB_BREAKPOINT",
    "USER_LISTENING", "TEST") describing the evidence's own nature;
    `detail` is a small dict of whatever fields make it reproducible
    (an address, a register value, a test name, a file path) -- kept as
    a plain dict rather than a rigid schema since different evidence
    kinds naturally carry different fields."""

    kind: str
    detail: dict = field(default_factory=dict)
    note: str = ""

    def to_dict(self) -> dict:
        return {"kind": self.kind, "detail": dict(self.detail), "note": self.note}

    @classmethod
    def from_dict(cls, d: dict) -> "Evidence":
        return cls(kind=d["kind"], detail=dict(d.get("detail", {})), note=d.get("note", ""))


@dataclass
class Claim:
    """A single claim (e.g. "CAP0.EXE's call site loads MPRO.EXE") with
    its current confidence tier and the evidence that backs it. Mirrors
    the exact JSON shape sketched in the toolkit-readiness audit's own
    brief for this module."""

    claim: str
    confidence: Confidence
    evidence: list[Evidence] = field(default_factory=list)

    def add_evidence(self, item: Evidence, *, new_confidence: Confidence | None = None) -> None:
        """Append new evidence, optionally updating the confidence tier.
        Does not enforce that `new_confidence` is stronger than the
        current one -- a DISPROVEN correction is a legitimate, expected
        use of this method, not a bug -- callers that want the "never
        downgrade a stronger claim by accident" behavior should check
        `is_stronger()` themselves before calling this."""
        self.evidence.append(item)
        if new_confidence is not None:
            self.confidence = new_confidence

    def to_dict(self) -> dict:
        return {
            "claim": self.claim,
            "confidence": self.confidence.value,
            "evidence": [e.to_dict() for e in self.evidence],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Claim":
        return cls(
            claim=d["claim"],
            confidence=Confidence(d["confidence"]),
            evidence=[Evidence.from_dict(e) for e in d.get("evidence", [])],
        )
