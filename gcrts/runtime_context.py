"""RuntimeContext model and resolver for the overlay engine
(`docs/overlay_engine/PS1_OVERLAY_RUNTIME_SYSTEM_DESIGN.md` §9).

This does not add any new detection capability -- it composes two
already-`CONFIRMED_LIVE` pieces this project already has
(`gcrts.overlay_identity.identify_overlay`,
`gcrts.movie_detection.classify_movie_state`) into the single
normalized structure the overlay engine's own spec calls for, with an
explicit confidence/evidence trail per field (`gcrts.evidence`), per
CTX-004 ("every resolved claim shall include a confidence/evidence
tier; unknown is a valid state").

Honest scope, stated up front rather than discovered later: this
resolver can tell you *which executable is resident* (real,
`CONFIRMED_LIVE`) and *whether a movie is active* (real,
`CONFIRMED_LIVE` for the detection mechanism itself). It can only
*guess* at the coarser MENU/GAMEPLAY/DIALOGUE distinction the spec's
`RuntimeContext.mode` field wants, via a small, explicitly-`INFERRED`
heuristic (`PROG.EXE` resident -> likely `MENU`, a `CAP*.EXE` resident
-> likely `GAMEPLAY`) based on a single observed screenshot from this
session, not a systematic study. `DIALOGUE` is not distinguishable at
all yet with current tools -- resolves to `UNKNOWN` rather than a
guess, per CTX-004's own "unknown is a valid state" principle.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from gcrts.evidence import Claim, Confidence, Evidence
from gcrts.movie_detection import MovieMatchConfidence, classify_movie_state
from gcrts.overlay_identity import OverlayProfile, identify_overlay


class RuntimeMode(str, Enum):
    BOOT = "BOOT"
    MENU = "MENU"
    GAMEPLAY = "GAMEPLAY"
    DIALOGUE = "DIALOGUE"
    MOVIE = "MOVIE"
    UNKNOWN = "UNKNOWN"


# Maps gcrts.movie_detection.MovieMatchConfidence -> gcrts.evidence.Confidence
# for the tiers that carry a genuinely equivalent meaning. AMBIGUOUS and
# NAME_MATCH don't have an exact equivalent in the shared tier set (they
# mean "multiple candidates" / "correlation, not independently checked"
# respectively) -- mapped to their closest honest equivalent rather than
# forced into an exact rename. NONE isn't mapped at all since it means
# "no movie active," which callers here never turn into a Claim about a
# movie in the first place.
_MOVIE_CONFIDENCE_MAP: dict[MovieMatchConfidence, Confidence] = {
    MovieMatchConfidence.CONFIRMED_LIVE: Confidence.CONFIRMED_LIVE,
    MovieMatchConfidence.AMBIGUOUS: Confidence.UNKNOWN,
    MovieMatchConfidence.NAME_MATCH: Confidence.INFERRED,
}


@dataclass
class RuntimeContext:
    game_id: str
    executable_id: str | None
    mode: RuntimeMode
    chapter_id: str | None = None
    scene_id: str | None = None
    dialogue_id: str | None = None
    movie_id: str | None = None
    audio_asset_id: str | None = None
    renderer_profile: str | None = None
    frame_counter: int | None = None
    claims: list[Claim] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "game_id": self.game_id,
            "executable_id": self.executable_id,
            "mode": self.mode.value,
            "chapter_id": self.chapter_id,
            "scene_id": self.scene_id,
            "dialogue_id": self.dialogue_id,
            "movie_id": self.movie_id,
            "audio_asset_id": self.audio_asset_id,
            "renderer_profile": self.renderer_profile,
            "frame_counter": self.frame_counter,
            "claims": [c.to_dict() for c in self.claims],
        }


# Explicitly INFERRED, not CONFIRMED_LIVE -- see module docstring.
_MENU_LIKE_PREFIXES = ("PROG.EXE",)
_GAMEPLAY_LIKE_PREFIXES = ("CAP0.EXE", "CAP1.EXE", "CAP2.EXE", "CAP3.EXE", "CAP4.EXE", "CAPX.EXE")


class RuntimeContextResolver:
    def __init__(self, game_id: str = "twilight_syndrome"):
        self.game_id = game_id

    def resolve(self, read_memory: Callable[[int, int], "bytes | None"]) -> RuntimeContext:
        overlay: OverlayProfile | None = identify_overlay(read_memory)
        claims: list[Claim] = []

        if overlay is None:
            claims.append(
                Claim(
                    claim="executable identity",
                    confidence=Confidence.UNKNOWN,
                    evidence=[Evidence(kind="CODE_SIGNATURE", note="no known signature matched live memory")],
                )
            )
            return RuntimeContext(game_id=self.game_id, executable_id=None, mode=RuntimeMode.UNKNOWN, claims=claims)

        claims.append(
            Claim(
                claim=f"resident executable is {overlay.name}",
                confidence=Confidence.CONFIRMED_LIVE,
                evidence=[Evidence(kind="CODE_SIGNATURE", detail={"pc0": hex(overlay.pc0), "t_addr": hex(overlay.t_addr)})],
            )
        )

        movie_result = classify_movie_state(overlay)
        movie_id = None
        mode = RuntimeMode.UNKNOWN
        if movie_result.movie_active:
            mode = RuntimeMode.MOVIE
            if len(movie_result.candidate_files) == 1:
                movie_id = movie_result.candidate_files[0]
            mapped_confidence = _MOVIE_CONFIDENCE_MAP.get(movie_result.confidence, Confidence.UNKNOWN)
            claims.append(
                Claim(
                    claim=f"movie active, candidate file(s): {list(movie_result.candidate_files)}",
                    confidence=mapped_confidence,
                    evidence=[Evidence(kind="OVERLAY_RESIDENCY", detail={"overlay": overlay.name})],
                )
            )
        elif overlay.name in _MENU_LIKE_PREFIXES:
            mode = RuntimeMode.MENU
            claims.append(
                Claim(
                    claim=f"mode is MENU while {overlay.name} is resident",
                    confidence=Confidence.INFERRED,
                    evidence=[Evidence(kind="OBSERVED_SCREENSHOT", note="based on one observed session screenshot, not a systematic study")],
                )
            )
        elif overlay.name in _GAMEPLAY_LIKE_PREFIXES:
            mode = RuntimeMode.GAMEPLAY
            claims.append(
                Claim(
                    claim=f"mode is GAMEPLAY while {overlay.name} is resident",
                    confidence=Confidence.INFERRED,
                    evidence=[Evidence(kind="OVERLAY_NAME_HEURISTIC", note="CAP*.EXE chapter overlays are assumed gameplay-context; not independently confirmed per-chapter")],
                )
            )
        else:
            claims.append(
                Claim(claim="coarse runtime mode", confidence=Confidence.UNKNOWN, evidence=[Evidence(kind="NONE", note="no mode heuristic covers this overlay")])
            )

        return RuntimeContext(
            game_id=self.game_id,
            executable_id=overlay.name,
            mode=mode,
            movie_id=movie_id,
            claims=claims,
        )
