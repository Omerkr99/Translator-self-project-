"""Audio Review Pipeline: batch-analyzes every channel in one pack and
generates human-reviewable artifacts (WAV files, `analysis.json`,
`ranking.csv`, `review.html`) so a person can confirm a channel's
semantic role in under a minute -- per the explicit project directive
that when human listening can resolve ambiguity quickly, the system
should prepare files/UI for that instead of spending effort on weaker
statistical inference alone.

This module is pure orchestration on top of already-proven layers:
`gcrts.xapack`/`gcrts.xapack_catalog` (physical structure, decoder),
`gcrts.audio_asset_resolver` (identity + decode), `gcrts.audio_semantic`
(feature extraction + heuristic candidate ranking), and
`gcrts.semantic_label_store` (human-confirmed labels, checked and
surfaced here so a reviewer never has to re-decide an already-confirmed
channel).
"""
from __future__ import annotations

import array
import csv
import json
import os
import wave
from dataclasses import dataclass

from gcrts.audio_semantic import (
    AudioFeatures,
    SemanticClassification,
    activity_window_features,
    compute_audio_features,
    rank_pack_channels,
)
from gcrts.semantic_label_store import DEFAULT_STORE_PATH as DEFAULT_LABEL_STORE_PATH
from gcrts.semantic_label_store import get_label
from gcrts.xapack import SAMPLES_PER_CHANNEL_PER_SECTOR, XaChannelStream, audio_asset_from_channel_stream
from gcrts.audio_asset_resolver import decode_audio_asset
from gcrts.xapack_catalog import catalog_entry_for_path
from gcrts.xapack import parse_pack_channel_streams, write_wav


def runtime_lba_to_offset_seconds(stream: XaChannelStream, runtime_lba: int) -> float | None:
    """Converts a live-observed physical LBA (which may have been read
    while ANY of the pack's 8 interleaved channels' sectors were
    passing under the head, not necessarily this channel's own) into
    an approximate elapsed-time offset INTO this specific channel's
    own stream. Returns None if the LBA falls outside this channel's
    own bounds. Approximate: assumes the standard 8-way interleave
    (confirmed structural fact, see gcrts.xapack's module docstring),
    not a precise per-sector guarantee."""
    if runtime_lba < stream.first_lba:
        return None
    if stream.eof_lba is not None and runtime_lba > stream.eof_lba:
        return None
    sectors_into_channel = (runtime_lba - stream.first_lba) // 8
    return sectors_into_channel * SAMPLES_PER_CHANNEL_PER_SECTOR / stream.format.sample_rate_hz


@dataclass(frozen=True)
class ChannelReviewEntry:
    asset_id: str
    features: AudioFeatures
    classification: SemanticClassification
    confirmed_label: dict | None
    activity_window: dict | None
    wav_filename: str


@dataclass(frozen=True)
class PackReviewResult:
    pack_path: str
    out_dir: str
    entries: tuple[ChannelReviewEntry, ...]
    runtime_anchor_lba: int | None


def build_pack_review(
    disc_bytes: bytes,
    pack_path: str,
    out_dir: str,
    runtime_anchor_lba: int | None = None,
    label_store_path: str = DEFAULT_LABEL_STORE_PATH,
) -> PackReviewResult:
    """The main entry point. Decodes every channel in `pack_path`,
    computes features, ranks candidates against each other (relative,
    within-pack -- see gcrts.audio_semantic), checks for any
    already-human-confirmed label, and writes WAV + analysis.json +
    ranking.csv + review.html into `out_dir`. `label_store_path`
    defaults to the project's real confirmed-label store; tests pass a
    temp path so they never read or write real project data."""
    os.makedirs(out_dir, exist_ok=True)
    pack = catalog_entry_for_path(pack_path)
    if pack is None:
        raise ValueError(f"Unknown pack path: {pack_path!r}")

    streams = parse_pack_channel_streams(disc_bytes, pack)
    assets = [audio_asset_from_channel_stream(s) for s in streams]

    all_features: list[AudioFeatures] = []
    pcm_by_asset: dict[str, tuple[int, array.array]] = {}
    for asset in assets:
        sr, channels, pcm = decode_audio_asset(disc_bytes, asset)
        samples = array.array("h")
        samples.frombytes(pcm)
        left = samples[0::channels] if channels == 2 else samples
        pcm_by_asset[asset.asset_id] = (sr, left)
        features = compute_audio_features(asset.asset_id, left, sr)
        all_features.append(features)

        wav_filename = f"{asset.asset_id.replace(':', '_ch')}.wav"
        write_wav(os.path.join(out_dir, wav_filename), sr, channels, pcm)

    classifications = rank_pack_channels(all_features)
    classification_by_id = {c.asset_id: c for c in classifications}

    entries = []
    for asset, features in zip(assets, all_features):
        stream = next(s for s in streams if s.channel_number == asset.channel_number)
        activity_window = None
        if runtime_anchor_lba is not None:
            offset = runtime_lba_to_offset_seconds(stream, runtime_anchor_lba)
            if offset is not None:
                activity_window = activity_window_features(features, offset)

        confirmed = get_label(asset.asset_id, path=label_store_path)
        entries.append(
            ChannelReviewEntry(
                asset_id=asset.asset_id,
                features=features,
                classification=classification_by_id[asset.asset_id],
                confirmed_label=confirmed.to_dict() if confirmed else None,
                activity_window=activity_window,
                wav_filename=f"{asset.asset_id.replace(':', '_ch')}.wav",
            )
        )

    # Re-sort entries the same way rank_pack_channels did, so the review
    # artifacts present the most dialogue-plausible candidates first.
    order = {c.asset_id: i for i, c in enumerate(classifications)}
    entries.sort(key=lambda e: order[e.asset_id])

    result = PackReviewResult(pack_path=pack_path, out_dir=out_dir, entries=tuple(entries), runtime_anchor_lba=runtime_anchor_lba)
    _write_analysis_json(result)
    _write_ranking_csv(result)
    _write_review_html(result)
    return result


def _write_analysis_json(result: PackReviewResult) -> None:
    data = {
        "pack_path": result.pack_path,
        "runtime_anchor_lba": result.runtime_anchor_lba,
        "channels": [
            {
                "asset_id": e.asset_id,
                "features": e.features.to_dict(),
                "classification": e.classification.to_dict(),
                "confirmed_label": e.confirmed_label,
                "activity_window": e.activity_window,
                "wav_filename": e.wav_filename,
            }
            for e in result.entries
        ],
    }
    with open(os.path.join(result.out_dir, "analysis.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _write_ranking_csv(result: PackReviewResult) -> None:
    path = os.path.join(result.out_dir, "ranking.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "asset_id", "semantic_type_candidate", "candidate_score", "confirmed_label",
            "duration_s", "rms_mean", "rms_cv", "silence_ratio", "burst_count",
            "avg_burst_duration_s", "spectral_centroid_hz", "notes",
        ])
        for e in result.entries:
            w.writerow([
                e.asset_id, e.classification.semantic_type.value, e.classification.candidate_score,
                e.confirmed_label["semantic_type"] if e.confirmed_label else "",
                round(e.features.duration_seconds, 2), round(e.features.rms_mean, 1),
                round(e.features.rms_cv, 2), round(e.features.silence_ratio, 3),
                e.features.burst_count, round(e.features.avg_burst_duration_s, 2),
                round(e.features.spectral_centroid_hz, 0), e.classification.notes,
            ])


def _envelope_svg(window_rms: tuple[float, ...], width: int = 400, height: int = 60) -> str:
    if not window_rms:
        return f'<svg width="{width}" height="{height}"></svg>'
    peak = max(window_rms) or 1.0
    n = len(window_rms)
    points = []
    for i, v in enumerate(window_rms):
        x = (i / max(1, n - 1)) * width
        y = height - (v / peak) * height
        points.append(f"{x:.1f},{y:.1f}")
    polyline = " ".join(points)
    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'style="background:#1a1a1a;border-radius:4px">'
        f'<polyline points="{polyline}" fill="none" stroke="#6ec1ff" stroke-width="1.5"/>'
        f"</svg>"
    )


def _write_review_html(result: PackReviewResult) -> None:
    pack_name = result.pack_path.rsplit("/", 1)[1]
    rows = []
    for e in result.entries:
        badge_color = {
            "DIALOGUE": "#4caf50", "MUSIC": "#ff9800", "AMBIENCE": "#9c27b0",
            "SILENCE": "#607d8b", "SFX": "#00bcd4", "UNKNOWN": "#757575",
        }.get(e.classification.semantic_type.value, "#757575")
        confirmed_html = ""
        if e.confirmed_label:
            confirmed_html = (
                f'<div style="margin-top:6px;padding:6px;background:#2e4a2e;border-radius:4px;">'
                f'<strong>CONFIRMED: {e.confirmed_label["semantic_type"]}</strong> '
                f'({e.confirmed_label["verification_source"]})<br>'
                f'<span style="opacity:0.8">{e.confirmed_label["notes"]}</span></div>'
            )
        activity_html = ""
        if e.activity_window and e.activity_window.get("available"):
            aw = e.activity_window
            activity_html = (
                f'<div style="margin-top:6px;font-size:0.85em;opacity:0.85">'
                f'runtime-anchor window @ {aw["offset_seconds"]:.1f}s: '
                f'relative activity {aw["relative_activity"]:.2f}x clip average</div>'
            )
        rows.append(f"""
        <div style="border:1px solid #444;border-radius:8px;padding:14px;margin-bottom:12px;background:#242424;">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <h3 style="margin:0;color:#eee;">{e.asset_id}</h3>
            <span style="background:{badge_color};color:#fff;padding:3px 10px;border-radius:12px;font-size:0.85em;">
              {e.classification.semantic_type.value} ({e.classification.candidate_score:.0%})
            </span>
          </div>
          <audio controls src="{e.wav_filename}" style="width:100%;margin:8px 0;"></audio>
          {_envelope_svg(e.features.window_rms)}
          <div style="margin-top:8px;font-size:0.85em;color:#bbb;">
            duration={e.features.duration_seconds:.2f}s &middot;
            rms_mean={e.features.rms_mean:.0f} &middot;
            rms_cv={e.features.rms_cv:.2f} &middot;
            silence={e.features.silence_ratio:.0%} &middot;
            bursts={e.features.burst_count} (avg {e.features.avg_burst_duration_s:.2f}s) &middot;
            centroid={e.features.spectral_centroid_hz:.0f}Hz
          </div>
          <div style="margin-top:6px;font-size:0.85em;color:#999;">{e.classification.notes}</div>
          {activity_html}
          {confirmed_html}
        </div>""")

    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Audio Review: {pack_name}</title></head>
<body style="font-family:system-ui,sans-serif;background:#161616;color:#eee;padding:24px;max-width:900px;margin:0 auto;">
<h1 style="color:#fff;">{pack_name} &mdash; Audio Review</h1>
<p style="color:#999;">
Candidates ranked by dialogue-plausibility (heuristic, NOT confirmed).
{"Runtime anchor LBA: " + str(result.runtime_anchor_lba) if result.runtime_anchor_lba else "No runtime anchor supplied."}
Listen to each clip and tell the assistant which one(s) are real dialogue
so it can be recorded permanently via gcrts.semantic_label_store.
</p>
{"".join(rows)}
</body></html>"""
    with open(os.path.join(result.out_dir, "review.html"), "w", encoding="utf-8") as f:
        f.write(html)
