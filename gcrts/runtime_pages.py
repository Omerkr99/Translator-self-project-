"""Stable-composition page candidates derived from runtime content, never
screenshots.

Milestone 7's own framing: pages are organization METADATA, never runtime
detection. `observe()` below only ever answers "have I seen this exact
asset composition before" (a factual, mechanical question) -- it never
assigns a page a semantic name ("Main Menu", "Photo Menu"), and every
auto-created page's `status` stays `CANDIDATE` with `name=None` forever
unless a user explicitly promotes it via `create_named_page()`. That
promotion, and `declare_variant()` below, are the only two ways a page
ever gets a name, an explicit required/optional/ignored boundary, or a
non-default matching mode -- never inferred automatically.
"""
from dataclasses import dataclass, field
from enum import Enum
import json
from pathlib import Path


class PageStatus:
    CANDIDATE = "CANDIDATE"  # auto-detected by observe(), unnamed, unreviewed
    USER_DEFINED = "USER_DEFINED"  # explicitly named/configured via create_named_page()


class MatchingMode(str, Enum):
    """7.3 -- never chosen automatically; a page keeps BALANCED (today's
    original Jaccard-similarity behavior) until a user picks something
    else via create_named_page()."""

    MANUAL_ONLY = "MANUAL_ONLY"  # never auto-matched by observe() -- only reachable by explicit user action (create_named_page/declare_variant)
    STRICT = "STRICT"  # required+optional must match the observed set exactly (after removing ignored assets)
    BALANCED = "BALANCED"  # Jaccard similarity over required+optional vs observed >= threshold -- the original, still the default
    LOOSE = "LOOSE"  # every required asset present is enough; missing optionals / extra unlisted assets don't matter
    CUSTOM = "CUSTOM"  # like BALANCED, but with a page-specific threshold (`custom_threshold`) instead of the detector's default


@dataclass
class RuntimePage:
    page_id: str
    core_assets: frozenset[str]  # the composition first observed for this page -- kept for audit/continuity, not used for matching once required/optional are set
    status: str = "CANDIDATE"
    name: str | None = None
    observations: int = 1
    required_assets: frozenset[str] = field(default_factory=frozenset)
    optional_assets: frozenset[str] = field(default_factory=frozenset)
    ignored_assets: frozenset[str] = field(default_factory=frozenset)
    matching_mode: str = MatchingMode.BALANCED.value
    custom_threshold: float | None = None
    variant_of: str | None = None  # 7.4 -- set only by declare_variant(), never inferred

    @property
    def is_user_defined(self) -> bool:
        return self.status == PageStatus.USER_DEFINED


def page_matches(page: RuntimePage, observed: frozenset[str], default_similarity: float) -> bool:
    """The matching decision for one page against one observed composition.
    A raw, never-promoted CANDIDATE (no required/optional ever set) keeps
    the exact original behavior: plain Jaccard similarity of its
    `core_assets` against the whole observed set. A USER_DEFINED page (or
    any page a user has given an explicit required/optional/ignored
    boundary) is judged only within that boundary, per its own
    `matching_mode` -- this is what makes 7.3's modes real rather than
    decorative fields nothing reads."""
    scope = page.required_assets | page.optional_assets
    if not scope:
        return RuntimePageDetector.score(page.core_assets, observed) >= default_similarity

    relevant = observed - page.ignored_assets
    mode = page.matching_mode
    if mode == MatchingMode.MANUAL_ONLY.value:
        return False
    if mode == MatchingMode.STRICT.value:
        return relevant == scope
    if mode == MatchingMode.LOOSE.value:
        return page.required_assets <= relevant
    threshold = default_similarity
    if mode == MatchingMode.CUSTOM.value and page.custom_threshold is not None:
        threshold = page.custom_threshold
    return RuntimePageDetector.score(scope, relevant) >= threshold


class RuntimePageDetector:
    def __init__(self, similarity=0.8):
        self.similarity = similarity
        self.pages: list[RuntimePage] = []
        self._next = 0

    @staticmethod
    def score(a, b):
        return len(a & b) / len(a | b) if a or b else 1.0

    def observe(self, asset_ids):
        assets = frozenset(asset_ids)
        candidates = [p for p in self.pages if page_matches(p, assets, self.similarity)]
        if candidates:
            match = max(candidates, key=lambda p: self.score(p.core_assets, assets))
            match.observations += 1
            return match, False
        self._next += 1
        page = RuntimePage(f"runtime.page.{self._next}", assets)
        self.pages.append(page)
        return page, True

    # --- 7.2: explicit, user-initiated page creation/promotion ------------
    def create_named_page(
        self,
        asset_ids,
        *,
        name: str,
        required=None,
        optional=None,
        ignored=None,
        matching_mode: MatchingMode | str = MatchingMode.BALANCED,
        custom_threshold: float | None = None,
        page_id: str | None = None,
    ) -> RuntimePage:
        """Never called by observe() -- this is the ONLY way a page gets a
        real name or an explicit required/optional/ignored boundary. If
        `page_id` names an existing page (typically a CANDIDATE the user
        is promoting from "Current Runtime Snapshot -> Create Page"), it's
        updated in place, keeping its observation history; otherwise a
        fresh USER_DEFINED page is created. `required` defaults to the
        full observed set (matches "this exact snapshot" until the user
        narrows it), `optional`/`ignored` default to empty."""
        observed = frozenset(asset_ids)
        mode_value = matching_mode.value if isinstance(matching_mode, MatchingMode) else matching_mode
        existing = next((p for p in self.pages if p.page_id == page_id), None) if page_id else None
        target = existing if existing is not None else RuntimePage(page_id or self._new_id(), observed, observations=0)
        target.name = name
        target.required_assets = frozenset(required) if required is not None else observed
        target.optional_assets = frozenset(optional) if optional is not None else frozenset()
        target.ignored_assets = frozenset(ignored) if ignored is not None else frozenset()
        target.matching_mode = mode_value
        target.custom_threshold = custom_threshold
        target.status = PageStatus.USER_DEFINED
        if existing is None:
            self.pages.append(target)
        return target

    def _new_id(self) -> str:
        self._next += 1
        return f"runtime.page.{self._next}"

    # --- 7.4: explicit variant grouping ------------------------------------
    def declare_variant(self, page_id: str, of_page_id: str) -> RuntimePage:
        """Mark `page_id` as a variant of `of_page_id` -- e.g. the same menu
        with a different highlighted selection. Purely a user decision:
        observe()'s similarity matching answers "is this the same runtime
        composition" (a mechanical fact); whether two DIFFERENT compositions
        should be treated as one conceptual Page is a judgment call only a
        person makes, per the milestone's own example."""
        page = next(p for p in self.pages if p.page_id == page_id)
        if of_page_id not in {p.page_id for p in self.pages}:
            raise ValueError(f"unknown page_id: {of_page_id!r}")
        page.variant_of = of_page_id
        return page

    def variants_of(self, page_id: str) -> list[RuntimePage]:
        return [p for p in self.pages if p.variant_of == page_id]

    def to_dict(self):
        return {
            "schema_version": 2,
            "pages": [
                {
                    "page_id": p.page_id,
                    "core_assets": sorted(p.core_assets),
                    "status": p.status,
                    "name": p.name,
                    "observations": p.observations,
                    "required_assets": sorted(p.required_assets),
                    "optional_assets": sorted(p.optional_assets),
                    "ignored_assets": sorted(p.ignored_assets),
                    "matching_mode": p.matching_mode,
                    "custom_threshold": p.custom_threshold,
                    "variant_of": p.variant_of,
                }
                for p in self.pages
            ],
        }

    def save(self, path):
        path = Path(path)
        if path.exists():
            try:
                disk = self.load(path, self.similarity)
                by_assets = {page.core_assets: page for page in disk.pages}
                for page in self.pages:
                    old = by_assets.get(page.core_assets)
                    if old:
                        old.observations = max(old.observations, page.observations)
                        old.status = page.status if old.status == "CANDIDATE" else old.status
                        old.name = old.name or page.name
                        # A USER_DEFINED page's explicit boundary/mode/variant always wins over
                        # whatever this in-memory instance had -- never silently overwritten by
                        # a re-save from a process that never saw the user's edits.
                        if page.status == PageStatus.USER_DEFINED or old.status != PageStatus.USER_DEFINED:
                            old.required_assets = page.required_assets or old.required_assets
                            old.optional_assets = page.optional_assets or old.optional_assets
                            old.ignored_assets = page.ignored_assets or old.ignored_assets
                            old.matching_mode = page.matching_mode
                            old.custom_threshold = page.custom_threshold
                            old.variant_of = page.variant_of or old.variant_of
                    else:
                        disk.pages.append(page)
                self.pages = disk.pages
                self._next = max(self._next, disk._next)
            except (OSError, json.JSONDecodeError, KeyError, ValueError):
                pass
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path, similarity=0.8):
        detector = cls(similarity)
        p = Path(path)
        if not p.exists():
            return detector
        data = json.loads(p.read_text(encoding="utf-8"))
        detector.pages = [
            RuntimePage(
                x["page_id"],
                frozenset(x["core_assets"]),
                x.get("status", "CANDIDATE"),
                x.get("name"),
                x.get("observations", 1),
                frozenset(x.get("required_assets", ())),
                frozenset(x.get("optional_assets", ())),
                frozenset(x.get("ignored_assets", ())),
                x.get("matching_mode", MatchingMode.BALANCED.value),
                x.get("custom_threshold"),
                x.get("variant_of"),
            )
            for x in data.get("pages", [])
        ]
        detector._next = max(
            (int(page.page_id.rsplit(".", 1)[-1]) for page in detector.pages if page.page_id.rsplit(".", 1)[-1].isdigit()),
            default=0,
        )
        return detector
