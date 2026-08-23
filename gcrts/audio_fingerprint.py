"""Audio Fingerprint: Phase 5/6 of the Audio Data Trace milestone --
matches a runtime-derived candidate audio clip (from
`gcrts.audio_data_trace`) against this project's own already-decoded,
already-verified `AudioAsset` catalog (`gcrts.audio_asset_resolver`),
never against filenames or LBA proximity alone.

## Method: normalized frame-feature cross-correlation

The simplest reliable, fully local, offline method for this project's
actual need (short voice clips, candidate may be a fragment starting
mid-line, minor gain/decode differences, no cloud dependency): each
clip is reduced to a short sequence of per-frame features (RMS energy
+ zero-crossing rate, both already-established, cheap signal-
processing primitives -- see `gcrts.audio_semantic`'s own use of the
same signals for classification, though that module's own helpers are
private and are not imported here; this module computes its own
frame-level version tuned for matching rather than classification).
Features are z-score normalized (zero mean, unit variance) per clip so
absolute loudness differences don't matter -- only the *shape* of the
energy contour does, which tolerates the "small gain differences,
silence before/after, minor decode differences" this milestone's brief
requires.

Matching slides the (typically shorter) candidate's feature sequence
across the reference's, computing a normalized correlation at every
valid offset, and reports the best offset plus its score. This is NOT
a perceptual/landmark hash like Shazam's -- it is deliberately simpler,
and documented honestly as a heuristic tuned for coarse "is this
clip present somewhere in this known asset" queries, not for noisy
real-world audio matching at scale. It requires no libraries beyond
numpy, already a real dependency of this project (`gcrts.audio_semantic`).

## Human verification remains mandatory

Every `MatchResult` carries a numeric similarity, never a verdict.
`gcrts.dialogue_database`'s own confirmed/unconfirmed distinction
already enforces that only `USER_LISTENING`/`RUNTIME_EVIDENCE` count
as confirmed -- a fingerprint match is `HEURISTIC` evidence at best,
however high its score, until a human actually listens.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

import numpy as np

FRAME_SIZE = 512  # samples per frame, at the common analysis rate below
FRAME_HOP = 256
COMMON_ANALYSIS_RATE = 8000  # Hz -- low enough to be cheap, high enough to preserve speech envelope/ZCR shape
FINGERPRINT_VERSION = 1


def _resample_linear(samples: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    """Simple linear-interpolation resampling -- adequate for this
    module's own frame-feature extraction (which itself smooths things
    further), not claimed as broadcast-quality resampling."""
    if src_rate == dst_rate or len(samples) == 0:
        return samples
    duration = len(samples) / src_rate
    dst_count = max(1, int(round(duration * dst_rate)))
    src_positions = np.linspace(0, len(samples) - 1, num=dst_count)
    return np.interp(src_positions, np.arange(len(samples)), samples)


def pcm_bytes_to_mono_float(pcm_bytes: bytes, channels: int) -> np.ndarray:
    """Signed 16-bit PCM (this project's own decoder output format,
    gcrts.xapack.decode_channel_to_pcm) -> mono float64 in [-1, 1]."""
    samples = np.frombuffer(pcm_bytes, dtype="<i2").astype(np.float64) / 32768.0
    if channels > 1:
        usable = len(samples) - (len(samples) % channels)
        samples = samples[:usable].reshape(-1, channels).mean(axis=1)
    return samples


def _frame_features(samples: np.ndarray) -> np.ndarray:
    """Per-frame [RMS energy, zero-crossing rate], z-score normalized
    per-clip across frames -- the actual fingerprint. Returns an (N, 2)
    array; N depends on clip length."""
    if len(samples) < FRAME_SIZE:
        # Too short for even one full frame -- pad with silence rather
        # than refusing outright, since a real candidate clip may
        # legitimately be very short.
        samples = np.pad(samples, (0, FRAME_SIZE - len(samples)))
    frames = []
    for start in range(0, len(samples) - FRAME_SIZE + 1, FRAME_HOP):
        window = samples[start:start + FRAME_SIZE]
        rms = float(np.sqrt(np.mean(window ** 2)))
        zcr = float(np.mean(np.abs(np.diff(np.sign(window))) > 0))
        frames.append((rms, zcr))
    arr = np.array(frames, dtype=np.float64)
    for col in range(arr.shape[1]):
        std = arr[:, col].std()
        mean = arr[:, col].mean()
        arr[:, col] = (arr[:, col] - mean) / std if std > 1e-9 else 0.0
    return arr


@dataclass
class Fingerprint:
    asset_id: str
    frames: np.ndarray  # (N, 2) -- RMS + ZCR, z-score normalized
    duration_seconds: float
    version: int = FINGERPRINT_VERSION

    def to_dict(self) -> dict:
        return {
            "asset_id": self.asset_id,
            "frames": self.frames.tolist(),
            "duration_seconds": self.duration_seconds,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Fingerprint":
        return cls(asset_id=d["asset_id"], frames=np.array(d["frames"], dtype=np.float64), duration_seconds=d["duration_seconds"], version=d.get("version", FINGERPRINT_VERSION))


def compute_fingerprint(asset_id: str, pcm_bytes: bytes, sample_rate: int, channels: int) -> Fingerprint:
    mono = pcm_bytes_to_mono_float(pcm_bytes, channels)
    resampled = _resample_linear(mono, sample_rate, COMMON_ANALYSIS_RATE)
    frames = _frame_features(resampled)
    duration = len(mono) / sample_rate if sample_rate else 0.0
    return Fingerprint(asset_id, frames, duration)


# --- reference database -------------------------------------------------------------


def build_reference_database(disc_bytes: bytes, assets) -> dict[str, Fingerprint]:
    """`assets` is a list of gcrts.xapack.AudioAsset (e.g. from
    gcrts.audio_asset_resolver.build_full_disc_asset_index) -- decodes
    each one with the EXISTING, already-verified decoder
    (gcrts.audio_asset_resolver.decode_audio_asset), never a
    reimplementation. Skips (does not raise on) any asset whose decode
    fails or produces empty PCM -- a real, if rare, possibility for a
    malformed/edge-case stream; the caller can inspect which asset_ids
    are missing from the returned dict."""
    from gcrts.audio_asset_resolver import decode_audio_asset

    db: dict[str, Fingerprint] = {}
    for asset in assets:
        try:
            sample_rate, channels, pcm = decode_audio_asset(disc_bytes, asset)
        except Exception:
            continue
        if not pcm:
            continue
        db[asset.asset_id] = compute_fingerprint(asset.asset_id, pcm, sample_rate, channels)
    return db


def save_fingerprint_db(db: dict[str, Fingerprint], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump({aid: fp.to_dict() for aid, fp in db.items()}, f)


def load_fingerprint_db(path: str) -> dict[str, Fingerprint]:
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return {aid: Fingerprint.from_dict(d) for aid, d in raw.items()}


# --- matching ------------------------------------------------------------------------


@dataclass
class MatchResult:
    asset_id: str
    similarity: float  # 0-1 heuristic score -- NEVER a confirmation, see module docstring
    offset_seconds: float  # best-matching start offset WITHIN the reference asset
    candidate_duration_seconds: float

    def to_dict(self) -> dict:
        return {
            "asset_id": self.asset_id, "similarity": self.similarity,
            "offset_seconds": self.offset_seconds, "candidate_duration_seconds": self.candidate_duration_seconds,
        }


def _best_offset_similarity(candidate_frames: np.ndarray, reference_frames: np.ndarray) -> tuple[float, int]:
    """Slides `candidate_frames` across `reference_frames`, returns
    (best_similarity, best_offset_frame_index). If the candidate is
    LONGER than the reference, the comparison is reversed (reference
    slides across candidate instead) -- a real possibility if the
    "candidate" turns out to actually contain more than one line."""
    if len(candidate_frames) > len(reference_frames):
        # Swap roles; the offset is then relative to the (shorter) reference sliding across the candidate, which
        # is far less useful to report -- treat as similarity-only in that case (offset 0).
        shorter, longer = reference_frames, candidate_frames
        swapped = True
    else:
        shorter, longer = candidate_frames, reference_frames
        swapped = False

    n = len(shorter)
    if n == 0 or len(longer) == 0:
        return 0.0, 0

    best_sim = -1.0
    best_offset = 0
    for offset in range(len(longer) - n + 1):
        window = longer[offset:offset + n]
        # Per-column Pearson correlation, averaged across the 2 feature columns.
        col_sims = []
        for col in range(shorter.shape[1]):
            a, b = shorter[:, col], window[:, col]
            if a.std() < 1e-9 or b.std() < 1e-9:
                col_sims.append(0.0)
                continue
            corr = float(np.corrcoef(a, b)[0, 1])
            col_sims.append(corr)
        sim = float(np.mean(col_sims))
        if sim > best_sim:
            best_sim = sim
            best_offset = offset
    if swapped:
        best_offset = 0
    # Pearson correlation is in [-1, 1]; map to [0, 1] for a plain "similarity" score.
    return max(0.0, (best_sim + 1.0) / 2.0), best_offset


def match_candidate(candidate_fp: Fingerprint, db: dict[str, Fingerprint], top_n: int = 5) -> list[MatchResult]:
    results = []
    frame_duration = FRAME_HOP / COMMON_ANALYSIS_RATE
    for asset_id, ref_fp in db.items():
        similarity, offset_frames = _best_offset_similarity(candidate_fp.frames, ref_fp.frames)
        results.append(MatchResult(asset_id, similarity, offset_frames * frame_duration, candidate_fp.duration_seconds))
    results.sort(key=lambda r: r.similarity, reverse=True)
    return results[:top_n]


# --- CLI ---------------------------------------------------------------------------

DEFAULT_DISC_PATH = "קיבצי דמה/Twilight Syndrome - Tansaku Hen (Japan).bin"
DEFAULT_DB_PATH = "audio_fingerprints.json"


def _cmd_build_db(args) -> int:
    from gcrts.audio_asset_resolver import build_full_disc_asset_index

    print(f"loading disc image: {args.disc}")
    with open(args.disc, "rb") as f:
        disc_bytes = f.read()
    print("indexing assets...")
    assets = build_full_disc_asset_index(disc_bytes)
    print(f"{len(assets)} assets found; decoding + fingerprinting (this can take a while)...")
    db = build_reference_database(disc_bytes, assets)
    save_fingerprint_db(db, args.out)
    print(f"wrote {len(db)} fingerprints to {args.out} ({len(assets) - len(db)} asset(s) failed to decode and were skipped)")
    return 0


def _cmd_match(args) -> int:
    from gcrts.xa_decoder_verify import read_wav_pcm

    sample_rate, channels, pcm = read_wav_pcm(args.candidate_wav)
    candidate_fp = compute_fingerprint("CANDIDATE", pcm, sample_rate, channels)
    db = load_fingerprint_db(args.db)
    results = match_candidate(candidate_fp, db, top_n=args.top)
    print(f"{len(results)} match(es), ranked by similarity (HEURISTIC evidence only -- human listening required before any confirmation):\n")
    print(f"{'Rank':<6}{'AudioAsset':<20}{'Similarity':>12}{'Offset (s)':>14}")
    for i, r in enumerate(results, start=1):
        print(f"{i:<6}{r.asset_id:<20}{r.similarity:>12.3f}{r.offset_seconds:>14.2f}")
    return 0


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Audio Fingerprint: match runtime audio candidates against the known AudioAsset catalog.")
    sub = parser.add_subparsers(dest="command", required=True)

    build_parser = sub.add_parser("build-db", help="Build the reference fingerprint database from the real disc image.")
    build_parser.add_argument("--disc", default=DEFAULT_DISC_PATH)
    build_parser.add_argument("--out", default=DEFAULT_DB_PATH)
    build_parser.set_defaults(func=_cmd_build_db)

    match_parser = sub.add_parser("match", help="Match a candidate WAV against the reference fingerprint database.")
    match_parser.add_argument("candidate_wav")
    match_parser.add_argument("--db", default=DEFAULT_DB_PATH)
    match_parser.add_argument("--top", type=int, default=5)
    match_parser.set_defaults(func=_cmd_match)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    import sys

    sys.exit(main())
