"""Binary Segmentation Engine (Phase 1 subset): raw file loading only.

Later phases will add entropy-based segmentation and content-type
classification. Phase 1 only needs to get the file's bytes into memory
along with basic size/path metadata for downstream engines.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class RawSegment:
    """The whole loaded file, treated as a single unclassified segment.

    Phase 1 does not split the file into TEXT/TEXTURE/FONT/UI/ANIMATION
    segments yet -- that is a Phase 2+ responsibility. This exists so the
    extractor has a stable object to work against instead of a bare
    bytes/path pair.
    """

    path: Path
    data: bytes
    kind: str = "UNKNOWN"

    @property
    def size(self) -> int:
        return len(self.data)


class BinaryLoader:
    """Loads a binary file (e.g. PS1 .BIN) fully into memory."""

    def load(self, file_path: str | Path) -> RawSegment:
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"No such file: {path}")

        data = path.read_bytes()
        return RawSegment(path=path, data=data)
