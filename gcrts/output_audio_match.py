"""Formalized workflow: emulator digital output -> source AudioAsset.

The method validated live this session (see
`docs/audio/OUTPUT_AUDIO_CAPTURE.md`): capture what actually reaches
the speakers (`gcrts.output_audio_capture`), localize the target line
from the audio's own acoustic shape, fingerprint-match against the
known `AudioAsset` catalog (`gcrts.audio_fingerprint`, already
independently validated), and require offset continuity across a
sliding window before trusting a match -- never a single whole-clip
score alone, which was shown live to produce a duration-mismatch false
lead (a high top score against references 5-50x shorter than the
query, sliding coincidentally into alignment).

    Play scene -> capture output -> localize line -> fingerprint ->
    continuity validation -> source excerpt -> USER_LISTENING -> store mapping

Every step here is a pure function operating on PCM samples/dicts, not
tied to any specific live session, so it can be tested with synthetic
signals without the real (gitignored) disc image -- consistent with
this project's established testing convention.
"""
from __future__ import annotations

import wave
from dataclasses import dataclass
from enum import Enum

import numpy as np

from gcrts.audio_fingerprint import Fingerprint, MatchResult, compute_fingerprint, match_candidate


# ---------------------------------------------------------------------------
# Phase: localize the target line from the capture's own acoustic shape
# ---------------------------------------------------------------------------

@dataclass
class EnergyWindow:
    t: float
    rms: float


def compute_energy_profile(samples: np.ndarray, sample_rate: int, window_seconds: float = 0.1) -> list[EnergyWindow]:
    """RMS energy per fixed-size window over a mono float/int signal.
    Pure, offline -- no live capture needed to compute this."""
    frame = max(1, int(sample_rate * window_seconds))
    n_windows = len(samples) // frame
    out = []
    for i in range(n_windows):
        seg = samples[i * frame:(i + 1) * frame].astype(np.float64)
        rms = float(np.sqrt(np.mean(seg ** 2))) if len(seg) else 0.0
        out.append(EnergyWindow(t=round(i * window_seconds, 3), rms=rms))
    return out


def find_speech_burst_region(
    profile: list[EnergyWindow],
    search_window_seconds: float = 8.0,
    min_rms: float = 5.0,
) -> tuple[float, float] | None:
    """Speech has natural pauses between phrases -- high variance
    relative to its own mean (bursts alternating with near-silence).
    Steady background music has the opposite shape: high mean, low
    relative variance. Scans candidate windows and picks the one with
    the highest coefficient of variation (std/mean) among windows that
    aren't just near-silence throughout.

    Returns (begin, end) in seconds, or None if nothing looks
    speech-shaped anywhere in the profile."""
    if not profile:
        return None
    dt = profile[1].t - profile[0].t if len(profile) > 1 else 0.1
    win_n = max(1, int(search_window_seconds / dt))
    rms = np.array([w.rms for w in profile])

    best_score = -1.0
    best_start = None
    step = max(1, win_n // 4)
    for start in range(0, len(rms) - win_n + 1, step):
        seg = rms[start:start + win_n]
        mean = seg.mean()
        if mean < min_rms:
            continue  # near-total silence, not a candidate
        std = seg.std()
        cov = std / mean if mean > 0 else 0.0
        if cov > best_score:
            best_score = cov
            best_start = start

    if best_start is None:
        return None

    # Refine: within the winning window, trim to where energy actually
    # rises above a floor near its own mean, so BEGIN/END aren't padded
    # with the window's own silent edges.
    seg = rms[best_start:best_start + win_n]
    floor = seg.mean() * 0.15
    active = np.where(seg > floor)[0]
    if len(active) == 0:
        first, last = 0, win_n - 1
    else:
        first, last = active[0], active[-1]
    begin = profile[best_start + first].t
    end = profile[best_start + last].t + dt
    return (begin, end)


# ---------------------------------------------------------------------------
# Phase: crop / normalize
# ---------------------------------------------------------------------------

def read_wav_samples(path: str) -> tuple[np.ndarray, int, int]:
    """Returns (samples shaped [n, channels] int16, sample_rate, channels)."""
    with wave.open(path, "rb") as wf:
        ch = wf.getnchannels()
        sr = wf.getframerate()
        data = wf.readframes(wf.getnframes())
    samples = np.frombuffer(data, dtype=np.int16).reshape(-1, ch)
    return samples, sr, ch


def write_wav_samples(path: str, samples: np.ndarray, sample_rate: int, channels: int) -> None:
    with wave.open(path, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(np.ascontiguousarray(samples, dtype=np.int16).tobytes())


def crop_excerpt(samples: np.ndarray, sample_rate: int, begin: float, end: float) -> np.ndarray:
    lo = max(0, int(begin * sample_rate))
    hi = min(len(samples), int(end * sample_rate))
    return samples[lo:hi]


def normalize_for_matching(samples: np.ndarray, target_peak: float = 0.9) -> np.ndarray:
    """DC-offset removal + peak gain normalization only -- deliberately
    no denoising/filtering, per this workflow's own governing
    principle (matching, not cosmetic cleanup)."""
    float_samples = samples.astype(np.float64)
    float_samples -= float_samples.mean(axis=0, keepdims=True)
    peak = np.abs(float_samples).max()
    if peak > 0:
        float_samples *= (target_peak * 32767.0) / peak
    return np.clip(float_samples, -32768, 32767).astype(np.int16)


# ---------------------------------------------------------------------------
# Phase: duration-plausible fingerprint match (avoids the short-clip artifact)
# ---------------------------------------------------------------------------

def filter_duration_plausible(
    db: dict[str, Fingerprint], query_duration: float, min_ratio: float = 0.3
) -> dict[str, Fingerprint]:
    """Excludes reference assets far shorter than the query. Live
    validation this session found the naive top match against an
    unfiltered database was a duration artifact: several references
    5-50x shorter than an 8.6s query all scored 0.87-0.98 by
    coincidentally sliding into local alignment. `min_ratio=0.3` keeps
    references at least 30% of the query's own length."""
    floor = query_duration * min_ratio
    return {aid: fp for aid, fp in db.items() if fp.duration_seconds >= floor}


# ---------------------------------------------------------------------------
# Phase: sliding-window offset-continuity search
# ---------------------------------------------------------------------------

@dataclass
class WindowMatch:
    window_start: float
    window_size: float
    asset_id: str
    similarity: float
    offset_seconds: float


def sliding_window_search(
    samples: np.ndarray,
    sample_rate: int,
    channels: int,
    db: dict[str, Fingerprint],
    window_sizes: tuple[float, ...] = (1.5,),
    hop_ratio: float = 0.5,
    top_n_per_window: int = 1,
) -> list[WindowMatch]:
    total_duration = len(samples) / sample_rate
    results: list[WindowMatch] = []
    for window_size in window_sizes:
        hop = window_size * hop_ratio
        t = 0.0
        while t + window_size <= total_duration:
            chunk = crop_excerpt(samples, sample_rate, t, t + window_size)
            fp = compute_fingerprint(f"w{t}", chunk.tobytes(), sample_rate, channels)
            for r in match_candidate(fp, db, top_n=top_n_per_window):
                results.append(WindowMatch(
                    window_start=round(t, 3), window_size=window_size,
                    asset_id=r.asset_id, similarity=r.similarity, offset_seconds=r.offset_seconds,
                ))
            t += hop
    return results


@dataclass
class ContinuityRun:
    asset_id: str
    window_size: float
    start_t: float
    end_t: float
    n_windows: int
    mean_similarity: float
    offset_advance_error: float  # mean abs difference between real-time delta and offset delta, seconds


def score_offset_continuity(
    window_matches: list[WindowMatch], hop_tolerance: float = 0.15
) -> list[ContinuityRun]:
    """Groups consecutive windows (same window_size, same asset,
    adjacent window_start) into runs, and scores how closely the
    asset's own matched offset advances with real elapsed time -- the
    signature this project's own live validation found distinguishes a
    real match (near-1:1 advance) from coincidental noise (chaotic,
    unrelated offsets from window to window)."""
    by_size: dict[float, list[WindowMatch]] = {}
    for m in window_matches:
        by_size.setdefault(m.window_size, []).append(m)

    runs: list[ContinuityRun] = []
    for window_size, matches in by_size.items():
        matches.sort(key=lambda m: m.window_start)
        i = 0
        while i < len(matches):
            run = [matches[i]]
            j = i + 1
            while j < len(matches):
                prev, cur = run[-1], matches[j]
                real_dt = cur.window_start - prev.window_start
                if cur.asset_id != prev.asset_id or real_dt <= 0:
                    break
                offset_dt = cur.offset_seconds - prev.offset_seconds
                if abs(offset_dt - real_dt) > hop_tolerance + real_dt * 0.5:
                    break
                run.append(cur)
                j += 1
            if len(run) >= 2:
                errors = [
                    abs((run[k].offset_seconds - run[k - 1].offset_seconds) - (run[k].window_start - run[k - 1].window_start))
                    for k in range(1, len(run))
                ]
                runs.append(ContinuityRun(
                    asset_id=run[0].asset_id, window_size=window_size,
                    start_t=run[0].window_start, end_t=run[-1].window_start + window_size,
                    n_windows=len(run), mean_similarity=sum(m.similarity for m in run) / len(run),
                    offset_advance_error=sum(errors) / len(errors) if errors else 0.0,
                ))
            i = j if j > i + 1 else i + 1
    runs.sort(key=lambda r: (r.n_windows, r.mean_similarity), reverse=True)
    return runs


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

class MatchClassification(str, Enum):
    VOICE_ASSET_MATCH_FOUND = "VOICE_ASSET_MATCH_FOUND"
    MULTIPLE_PLAUSIBLE_MATCHES = "MULTIPLE_PLAUSIBLE_MATCHES"
    NO_MATCH_IN_CURRENT_ASSET_DB = "NO_MATCH_IN_CURRENT_ASSET_DB"
    CAPTURE_INVALID = "CAPTURE_INVALID"


def classify_match(runs: list[ContinuityRun], min_run_windows: int = 3) -> MatchClassification:
    strong = [r for r in runs if r.n_windows >= min_run_windows and r.mean_similarity >= 0.85]
    if not strong:
        return MatchClassification.NO_MATCH_IN_CURRENT_ASSET_DB
    strong.sort(key=lambda r: (r.n_windows, r.mean_similarity), reverse=True)
    top = strong[0]
    others_close = [
        r for r in strong[1:]
        if r.asset_id != top.asset_id and r.n_windows >= top.n_windows * 0.7
    ]
    if others_close:
        return MatchClassification.MULTIPLE_PLAUSIBLE_MATCHES
    return MatchClassification.VOICE_ASSET_MATCH_FOUND


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cmd_main(argv: list[str] | None = None) -> int:
    import argparse
    import json
    import sys

    from gcrts.audio_fingerprint import load_fingerprint_db

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wav_path")
    parser.add_argument("--begin", type=float, default=None, help="target BEGIN in seconds; auto-localized if omitted")
    parser.add_argument("--end", type=float, default=None, help="target END in seconds; auto-localized if omitted")
    parser.add_argument("--db", default="audio_fingerprints.json")
    parser.add_argument("--window-sizes", default="0.5,1.0,1.5,2.0")
    args = parser.parse_args(argv)

    samples, sr, ch = read_wav_samples(args.wav_path)
    mono = samples.mean(axis=1)

    if args.begin is None or args.end is None:
        profile = compute_energy_profile(mono, sr)
        region = find_speech_burst_region(profile)
        if region is None:
            print(json.dumps({"classification": MatchClassification.CAPTURE_INVALID.value, "reason": "no speech-shaped region found"}))
            return 1
        begin, end = region
    else:
        begin, end = args.begin, args.end

    context = crop_excerpt(samples, sr, begin - 2.0, end + 2.0)
    context = normalize_for_matching(context)
    query_duration = end - begin

    db = load_fingerprint_db(args.db)
    plausible_db = filter_duration_plausible(db, query_duration)

    window_sizes = tuple(float(x) for x in args.window_sizes.split(","))
    window_matches = sliding_window_search(context, sr, ch, plausible_db, window_sizes=window_sizes)
    runs = score_offset_continuity(window_matches)
    classification = classify_match(runs)

    report = {
        "begin": begin, "end": end, "query_duration": query_duration,
        "classification": classification.value,
        "top_runs": [
            {"asset_id": r.asset_id, "window_size": r.window_size, "n_windows": r.n_windows,
             "mean_similarity": round(r.mean_similarity, 3), "offset_advance_error": round(r.offset_advance_error, 3)}
            for r in runs[:5]
        ],
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cmd_main())
