"""Audio Asset Index + Resolver: the runtime bridge from a live-observed
disc position (or a `ScriptAudioAssociation`) to a stable `AudioAsset`
identity (`gcrts.xapack`). Part of the "GCRTS XAPACK Raw Format + Audio
Asset Discovery" milestone (Phases 15/21/34/35).

Deliberately built on top of `gcrts.xapack`'s already-proven physical
structure rather than re-deriving anything: given any real LBA, this
module first finds which `XAPACK*.BIN` pack it falls inside
(`gcrts.xapack_catalog`), then which of that pack's (up to 8) physically
segmented channel streams it falls inside
(`gcrts.xapack.parse_pack_channel_streams`), and only then reports a
resolved `AudioAsset` -- never a guess, never a nearest-match.

`build_full_disc_asset_index` is the Phase 21 "persistent Audio Asset
Index" -- computed on demand from real disc bytes (a few seconds for the
whole disc, since it only scans sector metadata, never decodes audio),
not committed as a generated artifact (regenerating from the real disc
is cheap and always current; a stale committed copy would not be).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum

from gcrts.xa_disc_index import read_sector_meta
from gcrts.xapack import (
    AudioAsset,
    XaChannelStream,
    audio_asset_from_channel_stream,
    decode_channel_to_pcm,
    lba_falls_within_stream,
    mark_live_cross_validated,
    parse_pack_channel_streams,
    write_wav,
)
from gcrts.xapack_catalog import build_catalog, catalog_entry_for_lba, catalog_entry_for_path


class ResolutionConfidence(str, Enum):
    LIVE_LBA_MATCHED = "LIVE_LBA_MATCHED"  # the live LBA fell inside a real, structurally-bounded channel stream
    PACK_ONLY = "PACK_ONLY"  # LBA is inside a known pack, but not inside any parsed channel stream's own bounds
    UNRESOLVED = "UNRESOLVED"  # LBA is not inside any known XAPACK file at all


@dataclass(frozen=True)
class AudioAssetResolution:
    asset: AudioAsset | None
    confidence: ResolutionConfidence
    evidence: str
    live_lba: int | None

    def to_dict(self) -> dict:
        return {
            "asset": self.asset.to_dict() if self.asset is not None else None,
            "confidence": self.confidence.value,
            "evidence": self.evidence,
            "live_lba": self.live_lba,
        }


def resolve_audio_asset(disc_bytes: bytes, live_lba: int) -> AudioAssetResolution:
    """The Phase 34/35 runtime bridge: given one real, live-observed
    LBA (e.g. `RuntimeAudioEvent.start_lba`, already independently
    resolved to a source file by `gcrts.xa_disc_index`), find the
    physically-bounded `AudioAsset` it falls inside.

    IMPORTANT: because a pack's 8 channels are physically interleaved,
    their [first_lba, eof_lba] spans overlap almost entirely -- a
    single LBA can fall inside every channel's overall span at once.
    Range containment alone (`lba_falls_within_stream`) is therefore
    NOT enough to identify which channel a given LBA belongs to (a
    real bug caught during this milestone's own self-test: it picked
    channel 0 for a known channel-7 LBA, since channel 0's span also
    happened to cover it). The real channel identity must come from
    that exact sector's OWN subheader byte
    (`gcrts.xa_disc_index.read_sector_meta`), never inferred from span
    overlap -- this function reads it directly."""
    pack = catalog_entry_for_lba(live_lba)
    if pack is None:
        return AudioAssetResolution(
            asset=None,
            confidence=ResolutionConfidence.UNRESOLVED,
            evidence=f"LBA {live_lba} does not fall inside any known XAPACK file.",
            live_lba=live_lba,
        )

    meta = read_sector_meta(disc_bytes, live_lba)
    if meta is None:
        return AudioAssetResolution(
            asset=None,
            confidence=ResolutionConfidence.PACK_ONLY,
            evidence=f"LBA {live_lba} is inside {pack.disc_path} but its own sector has no valid sync/subheader.",
            live_lba=live_lba,
        )

    streams = parse_pack_channel_streams(disc_bytes, pack)
    for stream in streams:
        if stream.channel_number != meta.channel_number:
            continue
        if not lba_falls_within_stream(stream, live_lba):
            continue  # this channel's own sector at this LBA is padding/past its EOF, not live audio
        validated = mark_live_cross_validated(stream)
        asset = audio_asset_from_channel_stream(validated)
        return AudioAssetResolution(
            asset=asset,
            confidence=ResolutionConfidence.LIVE_LBA_MATCHED,
            evidence=(
                f"LBA {live_lba}'s own sector subheader reads channel "
                f"{meta.channel_number}, matching {pack.disc_path} channel "
                f"{stream.channel_number}'s physically-bounded stream "
                f"({stream.first_lba}-{stream.eof_lba})."
            ),
            live_lba=live_lba,
        )

    return AudioAssetResolution(
        asset=None,
        confidence=ResolutionConfidence.PACK_ONLY,
        evidence=(
            f"LBA {live_lba} is inside {pack.disc_path} (sector channel="
            f"{meta.channel_number}) but not within that channel's own "
            "parsed stream bounds (likely a silence-padding or terminator sector)."
        ),
        live_lba=live_lba,
    )


def resolve_from_script_audio_association(disc_bytes: bytes, association) -> AudioAssetResolution:
    """Phase 15: `ScriptAudioAssociation -> AudioAsset`. Takes the same
    `ScriptAudioAssociation` this project's `gcrts.script_audio_association`
    already builds and pulls the real, live-observed `start_lba` out of
    its embedded `audio_event` (a `RuntimeAudioEvent.to_dict()`) --
    never falls back to the raw `raw_parameter`/selector value, both
    already proven unstable elsewhere in this project."""
    audio_event = association.audio_event if isinstance(association, dict) else getattr(association, "audio_event", None)
    if not audio_event:
        return AudioAssetResolution(
            asset=None,
            confidence=ResolutionConfidence.UNRESOLVED,
            evidence="ScriptAudioAssociation has no attached audio_event to resolve an LBA from.",
            live_lba=None,
        )
    start_lba = audio_event.get("start_lba")
    if start_lba is None:
        return AudioAssetResolution(
            asset=None,
            confidence=ResolutionConfidence.UNRESOLVED,
            evidence="Attached audio_event has no resolved start_lba.",
            live_lba=None,
        )
    return resolve_audio_asset(disc_bytes, start_lba)


def _stream_for_asset(disc_bytes: bytes, asset: AudioAsset) -> XaChannelStream | None:
    """AudioAsset itself doesn't carry `xa_file_number` (only what's
    needed for identity/display) -- re-derive the full physical
    stream from its own pack_path/channel_number via a fresh, cheap
    pack parse (a single pack's worth of sector metadata, not the
    whole disc)."""
    pack = catalog_entry_for_path(asset.pack_path)
    if pack is None:
        return None
    for stream in parse_pack_channel_streams(disc_bytes, pack):
        if stream.channel_number == asset.channel_number:
            return stream
    return None


def decode_audio_asset(disc_bytes: bytes, asset: AudioAsset) -> tuple[int, int, bytes]:
    """Phase 21 safe playback backend: `AudioAsset -> (sample_rate,
    channels, pcm_bytes)`. Read-only -- never modifies the disc image
    or any extracted/decoded data it didn't just create. Raises
    ValueError if the asset's own pack/channel can no longer be found
    on the real disc (should not happen for an asset this project
    itself produced, but never silently returns garbage)."""
    stream = _stream_for_asset(disc_bytes, asset)
    if stream is None:
        raise ValueError(f"Could not re-derive a physical stream for asset {asset.asset_id!r}")
    return decode_channel_to_pcm(disc_bytes, stream)


def export_audio_asset_wav(disc_bytes: bytes, asset: AudioAsset, path: str) -> None:
    """Phase 21: `AudioAsset -> a real, playable .wav file on disk`.
    Read-only with respect to the disc/source data -- only ever writes
    the new, independent output file at `path`."""
    sample_rate, channels, pcm = decode_audio_asset(disc_bytes, asset)
    write_wav(path, sample_rate, channels, pcm)


def build_full_disc_asset_index(disc_bytes: bytes) -> list[AudioAsset]:
    """Phase 21: every real, structurally-derivable AudioAsset on the
    whole disc -- up to 8 per pack x 43 packs. Pure scan, no ADPCM
    decode (fast: a few seconds for the whole disc). Not cached to
    disk by this function; see save_asset_index/load_asset_index for
    an optional, explicit persistence step."""
    assets: list[AudioAsset] = []
    for pack in build_catalog():
        for stream in parse_pack_channel_streams(disc_bytes, pack):
            assets.append(audio_asset_from_channel_stream(stream))
    return assets


def save_asset_index(assets: list[AudioAsset], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump([a.to_dict() for a in assets], f, indent=2)


def load_asset_index(path: str) -> list[dict]:
    """Returns the raw dict records (not reconstructed AudioAsset
    objects -- AudioAsset's `format` field is a nested dataclass this
    project doesn't need a full round-trip deserializer for yet; the
    dicts are already useful for lookup/display)."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def find_asset_by_id(assets: list[AudioAsset], asset_id: str) -> AudioAsset | None:
    for asset in assets:
        if asset.asset_id == asset_id:
            return asset
    return None


def find_duplicate_assets(assets: list[AudioAsset]) -> dict[str, list[AudioAsset]]:
    """Phase 30: group assets by content fingerprint -- only assets
    that HAVE a computed `content_sha256` participate (fingerprinting
    is a separate, explicit step, see gcrts.xapack.fingerprint_bytes;
    this function never computes one itself). Returns only groups with
    more than one member."""
    by_hash: dict[str, list[AudioAsset]] = {}
    for asset in assets:
        if asset.content_sha256 is None:
            continue
        by_hash.setdefault(asset.content_sha256, []).append(asset)
    return {h: group for h, group in by_hash.items() if len(group) > 1}
