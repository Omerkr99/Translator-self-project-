"""Text Extraction Engine (Phase 2): multi-encoding text run extraction.

At each byte offset, every detector in gcrts.encoding.DETECTORS is tried and
the longest resulting match is kept -- this is how a UTF-16LE or Shift-JIS
run wins over being mis-read as isolated ASCII bytes. Ties are broken by
detector priority order (utf-16le > shift_jis > ascii), since the more
constrained encodings are less likely to match by coincidence.

`length` is the number of raw bytes the run spans (not the decoded
character count), so offset + length always points past the raw data the
string came from -- useful for later phases that need to preserve/patch the
original bytes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from gcrts.encoding import DETECTORS
from gcrts.loader import RawSegment


@dataclass
class ExtractedString:
    offset: int
    text: str
    encoding: str
    length: int

    def to_dict(self) -> dict:
        return asdict(self)


def extract_text_runs(segment: RawSegment, min_length: int = 4) -> list[ExtractedString]:
    """Scan a raw segment for ASCII / Shift-JIS / UTF-16LE text runs >= min_length bytes."""

    data = segment.data
    n = len(data)
    results: list[ExtractedString] = []
    i = 0

    while i < n:
        best = None
        best_span = 0
        for detector in DETECTORS:
            match = detector(data, i)
            if match is None:
                continue
            span = match.end - i
            if span > best_span:
                best = match
                best_span = span

        if best is None:
            i += 1
            continue

        if best_span >= min_length:
            results.append(
                ExtractedString(
                    offset=i, text=best.text, encoding=best.encoding, length=best_span
                )
            )

        i = best.end

    return results
