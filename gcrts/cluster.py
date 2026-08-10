"""Pattern Analysis + Clustering Engine (Phase 2 subset).

Implements the "close offsets -> same cluster" clustering rule: strings are
sorted by offset and grouped wherever the gap to the previous string's end
is within `max_gap` bytes. This gives sequential/proximity clustering only.

Two other clustering rules from the spec -- "repeated structure -> same
cluster" and semantic classification of clusters into dialogue/menu/system
-- require comparing cluster shape and content, which is Phase 3
(Classification) work and is not implemented here.
"""

from __future__ import annotations

from dataclasses import dataclass

from gcrts.extractor import ExtractedString


@dataclass
class TextCluster:
    cluster_id: int
    strings: list[ExtractedString]

    @property
    def start_offset(self) -> int:
        return self.strings[0].offset

    @property
    def end_offset(self) -> int:
        last = self.strings[-1]
        return last.offset + last.length

    def to_dict(self) -> dict:
        return {
            "cluster_id": self.cluster_id,
            "start_offset": self.start_offset,
            "end_offset": self.end_offset,
            "strings": [s.to_dict() for s in self.strings],
        }


def cluster_strings(
    strings: list[ExtractedString], max_gap: int = 32
) -> list[TextCluster]:
    """Group strings whose start is within max_gap bytes of the previous string's end.

    `strings` need not be pre-sorted -- they are sorted by offset first.
    """
    if not strings:
        return []

    ordered = sorted(strings, key=lambda s: s.offset)
    clusters: list[TextCluster] = []
    current = [ordered[0]]

    for prev, nxt in zip(ordered, ordered[1:]):
        gap = nxt.offset - (prev.offset + prev.length)
        if gap <= max_gap:
            current.append(nxt)
        else:
            clusters.append(TextCluster(cluster_id=len(clusters), strings=current))
            current = [nxt]

    clusters.append(TextCluster(cluster_id=len(clusters), strings=current))
    return clusters
