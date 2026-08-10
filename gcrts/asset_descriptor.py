"""Typed, serializable descriptors and safety policies for image assets."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class SizePolicy(str, Enum):
    EXACT_CONSUMED_SIZE = "EXACT_CONSUMED_SIZE"
    MAX_ALLOCATED_SIZE = "MAX_ALLOCATED_SIZE"
    RELOCATABLE = "RELOCATABLE"
    UNKNOWN = "UNKNOWN"


class VerificationStatus(str, Enum):
    LIVE_VERIFIED = "LIVE_VERIFIED"
    OFFLINE_CONFIRMED = "OFFLINE_CONFIRMED"
    IMPLEMENTED = "IMPLEMENTED"
    PARTIAL = "PARTIAL"
    EXPERIMENTAL = "EXPERIMENTAL"
    UNKNOWN = "UNKNOWN"
    UNSUPPORTED = "UNSUPPORTED"
    RULED_OUT = "RULED_OUT"


class SemanticStatus(str, Enum):
    KNOWN_SEMANTIC = "KNOWN_SEMANTIC"
    UNKNOWN_SEMANTIC = "UNKNOWN_SEMANTIC"


@dataclass(frozen=True)
class AssetSource:
    type: str
    path: str


@dataclass(frozen=True)
class ContainerLocation:
    type: str
    block: int
    compressed_offset: int
    compressed_size: int
    decoded_size: int | None = None


@dataclass(frozen=True)
class ImageMetadata:
    format: str
    width: int
    height: int
    palette_colors: int = 0


@dataclass(frozen=True)
class EncodingPolicy:
    size_mode: SizePolicy
    original_size: int | None = None


@dataclass(frozen=True)
class ScreenMapping:
    status: str = "UNKNOWN"
    bounds: tuple[int, int, int, int] | None = None


@dataclass(frozen=True)
class AssetCapabilities:
    view: bool = True
    export_png: bool = False
    replace_png: bool = False
    pixel_edit: bool = False
    palette_edit: bool = False
    text_overlay: bool = False
    reencode: bool = False
    temporary_inject: bool = False
    persistent_rebuild: bool = False


@dataclass(frozen=True)
class AssetDescriptor:
    id: str
    display_name: str
    game: str
    source: AssetSource
    container: ContainerLocation
    image: ImageMetadata
    encoding_policy: EncodingPolicy
    semantic_status: SemanticStatus = SemanticStatus.UNKNOWN_SEMANTIC
    usage: str = "unknown"
    screen_mapping: ScreenMapping = field(default_factory=ScreenMapping)
    runtime: dict[str, Any] = field(default_factory=dict)
    verification: dict[str, Any] = field(default_factory=dict)
    capabilities: AssetCapabilities = field(default_factory=AssetCapabilities)

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.id or not self.source.path:
            errors.append("asset id and source path are required")
        if self.container.block < 0 or self.container.compressed_offset < 0:
            errors.append("container block/offset must be non-negative")
        if self.container.compressed_size <= 0:
            errors.append("compressed size must be positive")
        if self.image.width <= 0 or self.image.height <= 0:
            errors.append("image dimensions must be positive")
        if self.encoding_policy.size_mode == SizePolicy.EXACT_CONSUMED_SIZE:
            if self.encoding_policy.original_size != self.container.compressed_size:
                errors.append("exact-size policy must equal the original consumed size")
        if self.encoding_policy.size_mode == SizePolicy.UNKNOWN and self.capabilities.reencode:
            errors.append("UNKNOWN size policy cannot advertise re-encoding")
        return errors

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["encoding_policy"]["size_mode"] = self.encoding_policy.size_mode.value
        value["semantic_status"] = self.semantic_status.value
        if value["screen_mapping"]["bounds"] is not None:
            value["screen_mapping"]["bounds"] = list(value["screen_mapping"]["bounds"])
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "AssetDescriptor":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        data = {k: v for k, v in value.items() if k in known}
        data["source"] = AssetSource(**data["source"])
        data["container"] = ContainerLocation(**data["container"])
        data["image"] = ImageMetadata(**data["image"])
        ep = data["encoding_policy"]
        data["encoding_policy"] = EncodingPolicy(SizePolicy(ep["size_mode"]), ep.get("original_size"))
        data["semantic_status"] = SemanticStatus(data.get("semantic_status", "UNKNOWN_SEMANTIC"))
        data["screen_mapping"] = ScreenMapping(**data.get("screen_mapping", {}))
        data["capabilities"] = AssetCapabilities(**data.get("capabilities", {}))
        return cls(**data)
