"""Semantic Audio Classification -- the third of four deliberately
separated layers this project now maintains for every piece of audio
on the disc:

```
Source identity   -- ScriptUnit -> XAPACK -> channel   (gcrts.audio_asset_resolver)
Physical format    -- XA_ADPCM, sector layout, etc.     (gcrts.xapack)
Semantic role       -- what a channel actually CONTAINS  (this module)
Product access      -- Play / Export / Translate / Replace (future UI layer)
```

Knowing the physical format does NOT mean the semantic role is known.
`classify_stream_format()` returning `XA_ADPCM` says nothing about
whether a given channel holds dialogue, music, ambience, or silence --
conflating those two questions was an explicit mistake earlier
sessions were warned against repeating.

## Confidence discipline

Automated analysis in this module (`classify_candidate`,
`rank_pack_channels`) only ever produces a *candidate* `SemanticType`
with a numeric score and `VerificationSource.HEURISTIC` provenance --
it never claims a channel IS confirmed dialogue. Only two things can
promote a label to confirmed: a human explicitly listening
(`VerificationSource.USER_LISTENING`) or real runtime evidence (a
live-observed LBA landing inside the asset during an independently
confirmed audible moment, `VerificationSource.RUNTIME_EVIDENCE`).
Once confirmed, `gcrts.semantic_label_store` persists the label and
nothing in this project re-guesses it automatically without
contradictory evidence -- see that module's own docstring.

## Why relative, within-pack comparison

Absolute thresholds on a single channel's RMS/silence-ratio are weak
evidence (real content varies too much pack to pack). Comparing a
channel against its own siblings in the *same* pack is much stronger:
if 6 of 8 channels in a pack look similar and one or two are outliers
with a transient, bursty envelope, that deviation is real, structural
evidence worth a human's attention -- regardless of what the absolute
numbers are. `classify_candidate` and `rank_pack_channels` are built
around this comparison, not fixed cutoffs.
"""
from __future__ import annotations

import array
import math
from dataclasses import dataclass
from enum import Enum

import numpy as np


class SemanticType(str, Enum):
    DIALOGUE = "DIALOGUE"
    SFX = "SFX"
    AMBIENCE = "AMBIENCE"
    MUSIC = "MUSIC"
    SILENCE = "SILENCE"
    UNKNOWN = "UNKNOWN"


class VerificationSource(str, Enum):
    USER_LISTENING = "USER_LISTENING"
    RUNTIME_EVIDENCE = "RUNTIME_EVIDENCE"
    HEURISTIC = "HEURISTIC"
    UNVERIFIED = "UNVERIFIED"


@dataclass(frozen=True)
class AudioFeatures:
    asset_id: str
    duration_seconds: float
    sample_rate_hz: int
    window_seconds: float
    rms_mean: float
    rms_stdev: float
    rms_cv: float  # coefficient of variation -- 0 for a perfectly steady tone/loop, high for bursty content
    silence_ratio: float  # fraction of windows below 10% of the clip's own mean RMS
    burst_count: int  # contiguous above-threshold window runs
    avg_burst_duration_s: float
    burst_regularity_cv: float  # coefficient of variation OF BURST LENGTHS -- low = regular/loop-like, high = irregular/speech-plausible
    silence_gap_count: int
    avg_silence_gap_s: float
    spectral_centroid_hz: float
    zero_crossing_rate: float
    window_rms: tuple[float, ...]  # raw per-window RMS series -- envelope viz / cross-channel correlation

    def to_dict(self) -> dict:
        return {
            "asset_id": self.asset_id,
            "duration_seconds": self.duration_seconds,
            "sample_rate_hz": self.sample_rate_hz,
            "window_seconds": self.window_seconds,
            "rms_mean": self.rms_mean,
            "rms_stdev": self.rms_stdev,
            "rms_cv": self.rms_cv,
            "silence_ratio": self.silence_ratio,
            "burst_count": self.burst_count,
            "avg_burst_duration_s": self.avg_burst_duration_s,
            "burst_regularity_cv": self.burst_regularity_cv,
            "silence_gap_count": self.silence_gap_count,
            "avg_silence_gap_s": self.avg_silence_gap_s,
            "spectral_centroid_hz": self.spectral_centroid_hz,
            "zero_crossing_rate": self.zero_crossing_rate,
            "window_rms": list(self.window_rms),
        }


def _window_rms_series(samples: np.ndarray, sample_rate_hz: int, window_seconds: float) -> list[float]:
    window = max(1, int(sample_rate_hz * window_seconds))
    series = []
    for i in range(0, len(samples), window):
        chunk = samples[i:i + window]
        if len(chunk) == 0:
            continue
        series.append(float(np.sqrt(np.mean(chunk.astype(np.float64) ** 2))))
    return series


def _bursts_and_gaps(window_rms: list[float], mean_rms: float, window_seconds: float) -> tuple[int, float, int, float, float]:
    """Returns (burst_count, avg_burst_duration_s, gap_count,
    avg_gap_duration_s, burst_regularity_cv). `burst_regularity_cv` is
    the coefficient of variation OF THE BURST LENGTHS THEMSELVES --
    low (near 0) means every burst is roughly the same length, the
    signature of a looping/rhythmic pattern (music, a repeating SFX);
    high means burst lengths vary a lot, more consistent with real
    speech (words and phrases are not uniform length). This is a
    different, complementary signal from `rms_cv` (which only measures
    overall amplitude variance and cannot tell a regular loop from
    genuinely irregular content -- a real confusion this project's own
    classifier first shipped with, see this module's own docstring)."""
    if not window_rms or mean_rms <= 0:
        return 0, 0.0, 0, 0.0, 0.0
    threshold = mean_rms * 0.3
    above = [w > threshold for w in window_rms]

    def _runs(flags: list[bool]) -> list[int]:
        runs, current = [], 0
        for f in flags:
            if f:
                current += 1
            elif current:
                runs.append(current)
                current = 0
        if current:
            runs.append(current)
        return runs

    burst_runs = _runs(above)
    gap_runs = _runs([not a for a in above])
    burst_count = len(burst_runs)
    gap_count = len(gap_runs)
    avg_burst = (sum(burst_runs) / burst_count * window_seconds) if burst_count else 0.0
    avg_gap = (sum(gap_runs) / gap_count * window_seconds) if gap_count else 0.0

    if burst_count >= 2:
        burst_mean = sum(burst_runs) / burst_count
        burst_stdev = math.sqrt(sum((b - burst_mean) ** 2 for b in burst_runs) / burst_count)
        burst_regularity_cv = burst_stdev / burst_mean if burst_mean > 0 else 0.0
    else:
        burst_regularity_cv = 0.0  # 0 or 1 bursts: not enough to judge regularity either way

    return burst_count, avg_burst, gap_count, avg_gap, burst_regularity_cv


def _spectral_centroid_hz(samples: np.ndarray, sample_rate_hz: int) -> float:
    if len(samples) < 2:
        return 0.0
    windowed = samples.astype(np.float64) * np.hanning(len(samples))
    spectrum = np.abs(np.fft.rfft(windowed))
    freqs = np.fft.rfftfreq(len(samples), d=1.0 / sample_rate_hz)
    total = spectrum.sum()
    if total <= 0:
        return 0.0
    return float((freqs * spectrum).sum() / total)


def _zero_crossing_rate(samples: np.ndarray) -> float:
    if len(samples) < 2:
        return 0.0
    signs = np.sign(samples)
    signs[signs == 0] = 1
    return float(np.mean(signs[:-1] != signs[1:]))


def compute_audio_features(asset_id: str, samples_left: array.array, sample_rate_hz: int, window_seconds: float = 0.5) -> AudioFeatures:
    """Pure feature extraction from already-decoded mono/left-channel
    16-bit PCM samples (a caller decodes via `gcrts.xapack`/
    `gcrts.audio_asset_resolver` first -- this function does no I/O
    and no disc access)."""
    arr = np.array(samples_left, dtype=np.int16)
    duration = len(arr) / sample_rate_hz if sample_rate_hz else 0.0

    window_rms = _window_rms_series(arr, sample_rate_hz, window_seconds)
    mean_rms = float(np.mean(window_rms)) if window_rms else 0.0
    stdev_rms = float(np.std(window_rms)) if window_rms else 0.0
    cv = stdev_rms / mean_rms if mean_rms > 0 else 0.0

    if not window_rms or mean_rms <= 0:
        silence_ratio = 1.0  # an all-zero clip is trivially 100% silent -- mean_rms*0.1 would wrongly be 0 too
    else:
        silence_threshold = mean_rms * 0.1
        silence_ratio = sum(1 for w in window_rms if w < silence_threshold) / len(window_rms)

    burst_count, avg_burst, gap_count, avg_gap, burst_regularity_cv = _bursts_and_gaps(window_rms, mean_rms, window_seconds)

    centroid = _spectral_centroid_hz(arr, sample_rate_hz)
    zcr = _zero_crossing_rate(arr)

    return AudioFeatures(
        asset_id=asset_id,
        duration_seconds=duration,
        sample_rate_hz=sample_rate_hz,
        window_seconds=window_seconds,
        rms_mean=mean_rms,
        rms_stdev=stdev_rms,
        rms_cv=cv,
        silence_ratio=silence_ratio,
        burst_count=burst_count,
        avg_burst_duration_s=avg_burst,
        burst_regularity_cv=burst_regularity_cv,
        silence_gap_count=gap_count,
        avg_silence_gap_s=avg_gap,
        spectral_centroid_hz=centroid,
        zero_crossing_rate=zcr,
        window_rms=tuple(window_rms),
    )


@dataclass(frozen=True)
class SemanticClassification:
    asset_id: str
    semantic_type: SemanticType
    candidate_score: float  # 0-1: confidence in the CANDIDATE guess, never "ground truth"
    verification_source: VerificationSource
    notes: str

    def to_dict(self) -> dict:
        return {
            "asset_id": self.asset_id,
            "semantic_type": self.semantic_type.value,
            "candidate_score": self.candidate_score,
            "verification_source": self.verification_source.value,
            "notes": self.notes,
        }


def _relative_stats(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 1.0
    mean = sum(values) / len(values)
    stdev = math.sqrt(sum((v - mean) ** 2 for v in values) / len(values)) if len(values) > 1 else 0.0
    return mean, stdev or 1.0


def classify_candidate(features: AudioFeatures, sibling_features: list[AudioFeatures]) -> SemanticClassification:
    """Relative, within-pack candidate classification. `sibling_features`
    should be every OTHER channel's features from the same pack
    (excluding `features` itself) -- comparison against siblings, not
    an absolute threshold, per this module's own docstring. Always
    returns `VerificationSource.HEURISTIC`; never `DIALOGUE` alone is
    treated as confirmed anywhere downstream."""
    if features.rms_mean <= 0 or features.silence_ratio > 0.95:
        return SemanticClassification(
            features.asset_id, SemanticType.SILENCE, 0.9, VerificationSource.HEURISTIC,
            "Near-zero RMS or >95% silent windows.",
        )

    if not sibling_features:
        return SemanticClassification(
            features.asset_id, SemanticType.UNKNOWN, 0.0, VerificationSource.HEURISTIC,
            "No sibling channels supplied for relative comparison.",
        )

    sib_cv = [s.rms_cv for s in sibling_features]
    sib_silence = [s.silence_ratio for s in sibling_features]
    sib_burst_dur = [s.avg_burst_duration_s for s in sibling_features]
    sib_centroid = [s.spectral_centroid_hz for s in sibling_features]

    cv_mean, cv_std = _relative_stats(sib_cv)
    silence_mean, silence_std = _relative_stats(sib_silence)
    burst_mean, burst_std = _relative_stats(sib_burst_dur)

    cv_z = (features.rms_cv - cv_mean) / cv_std
    burst_z = (features.avg_burst_duration_s - burst_mean) / burst_std

    # Speech-plausible signature, relative to siblings: noticeably
    # burstier envelope (high cv_z) with SHORT individual bursts
    # (speech syllables/words, not one long sustained tone) and a
    # meaningful silence ratio (pauses between words/sentences).
    is_bursty_outlier = cv_z > 0.75
    has_short_bursts = features.avg_burst_duration_s > 0 and features.avg_burst_duration_s < (burst_mean + burst_std if burst_std else burst_mean * 1.5 or 1.0)
    has_real_pauses = 0.05 < features.silence_ratio < 0.6

    # A real, diagnosed false-positive this classifier first shipped
    # with: a high-cv envelope with MULTIPLE, REGULARLY-SPACED bursts
    # (near-identical burst lengths) is the signature of a rhythmic
    # loop/repeating SFX, not speech -- real speech's word/phrase
    # lengths vary. Require irregularity (or too few bursts to judge)
    # before trusting the bursty-outlier signal as dialogue-plausible.
    is_regular_loop = features.burst_count >= 3 and features.burst_regularity_cv < 0.3

    if is_bursty_outlier and has_real_pauses and not is_regular_loop:
        score = min(0.85, 0.5 + cv_z * 0.15)
        return SemanticClassification(
            features.asset_id, SemanticType.DIALOGUE, round(score, 2), VerificationSource.HEURISTIC,
            f"Outlier vs siblings (cv_z={cv_z:.2f}), bursty envelope with real silence gaps "
            f"({features.silence_ratio:.0%}) and irregular burst lengths "
            f"(burst_regularity_cv={features.burst_regularity_cv:.2f}) -- speech-plausible, NOT confirmed.",
        )

    if is_bursty_outlier and has_real_pauses and is_regular_loop:
        return SemanticClassification(
            features.asset_id, SemanticType.MUSIC, 0.5, VerificationSource.HEURISTIC,
            f"Outlier vs siblings (cv_z={cv_z:.2f}) but {features.burst_count} bursts are "
            f"near-uniform length (burst_regularity_cv={features.burst_regularity_cv:.2f}) -- "
            "rhythmic loop/repeating-SFX-plausible, not speech.",
        )

    if features.rms_cv < (cv_mean - 0.5 * cv_std) and features.silence_ratio < 0.1:
        return SemanticClassification(
            features.asset_id, SemanticType.MUSIC, 0.55, VerificationSource.HEURISTIC,
            "Steadier envelope than siblings, low silence ratio -- loop/BGM-plausible.",
        )

    if features.rms_mean < (sum(s.rms_mean for s in sibling_features) / len(sibling_features)) * 0.4:
        return SemanticClassification(
            features.asset_id, SemanticType.AMBIENCE, 0.4, VerificationSource.HEURISTIC,
            "Quiet relative to siblings, not silent -- ambience-plausible.",
        )

    return SemanticClassification(
        features.asset_id, SemanticType.UNKNOWN, 0.3, VerificationSource.HEURISTIC,
        "No feature stood out clearly relative to sibling channels.",
    )


def rank_pack_channels(all_features: list[AudioFeatures]) -> list[SemanticClassification]:
    """Classify every channel in a pack against its own siblings.
    Returns results sorted by descending DIALOGUE-candidate score
    first (most speech-plausible first), never a claim of certainty."""
    results = []
    for f in all_features:
        siblings = [s for s in all_features if s.asset_id != f.asset_id]
        results.append(classify_candidate(f, siblings))
    results.sort(key=lambda r: (r.semantic_type != SemanticType.DIALOGUE, -r.candidate_score))
    return results


def activity_window_features(features: AudioFeatures, offset_seconds: float, window_seconds: float = 2.0) -> dict:
    """Phase: runtime-anchor-relative comparison. Given a known
    runtime-confirmed offset INTO this asset (see
    gcrts.audio_review.runtime_lba_to_offset_seconds), extract just
    the local RMS window around that point -- comparing sibling
    channels at the SAME relative moment is much stronger evidence
    than comparing whole-clip averages."""
    if not features.window_rms or features.window_seconds <= 0:
        return {"available": False}
    start_idx = max(0, int((offset_seconds - window_seconds / 2) / features.window_seconds))
    end_idx = min(len(features.window_rms), int((offset_seconds + window_seconds / 2) / features.window_seconds) + 1)
    local = features.window_rms[start_idx:end_idx]
    if not local:
        return {"available": False}
    return {
        "available": True,
        "offset_seconds": offset_seconds,
        "window_seconds": window_seconds,
        "local_rms_mean": sum(local) / len(local),
        "local_rms_max": max(local),
        "whole_clip_rms_mean": features.rms_mean,
        "relative_activity": (sum(local) / len(local)) / features.rms_mean if features.rms_mean > 0 else 0.0,
    }
