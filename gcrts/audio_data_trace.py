"""Audio Data Trace: the pivot from control-flow tracing to data
tracing. The SPU Playback Trace milestone's live Exec-breakpoint
approach (`gcrts.spu_playback_trace`/`pcsx_lua/spu_playback_trace.lua`)
reached diminishing returns this session -- repeated live captures
stopped early regardless of which breakpoints were armed, which save
slot was used, or how the write path was tuned, while `GPU::Vsync`
itself kept firing throughout (confirmed via a separately-created,
disposable listener). That is real, reproducible evidence that the
instability is NOT in this project's own control-flow instrumentation
logic -- but it also means continuing to chase code breakpoints
further is not the productive next move.

This module answers a different question: not "which code executes
when the line is heard," but "which bytes in RAM actually change while
the line is heard." It works entirely OFFLINE, on RAM snapshots
already captured to disk (`pcsx_lua/dump_ram.lua` produces those, on
explicit command only -- no continuous 60Hz capture loop, learning
directly from this session's own "don't run expensive work inside the
emulator" lesson).

## Pipeline

    BEFORE / DURING / AFTER snapshots (raw main-RAM dumps)
      -> diff_regions()          -- cluster changed bytes into contiguous regions
      -> compute_region_stats()  -- entropy, zero-density, etc. per region
      -> score_candidate_region() -- multi-signal ranking, never entropy-alone
      -> audio-likeness heuristics (spu_adpcm_score / xa_like_score / pcm_score)
      -> extract_candidate_wav() -- for a region that decodes plausibly

`gcrts.audio_fingerprint` picks up from an extracted candidate WAV and
matches it against the existing, already-proven `AudioAsset` catalog
(`gcrts.audio_asset_resolver`) -- never against filenames or LBA
proximity alone.

## What this module deliberately does NOT do

Does not fabricate an audio classification from entropy alone --
`score_candidate_region` combines several signals (see its own
docstring) specifically because high entropy is necessary but nowhere
near sufficient evidence (compressed non-audio game data is high
entropy too). Does not claim a code writer/consumer for any region --
that is Phase 7/8 of the milestone's own plan, deliberately gated on
having a real, reproducible candidate region first ("no new code
breakpoint without a data region that justifies it").
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from enum import Enum

import numpy as np


# --- snapshot loading + metadata --------------------------------------------------


def compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_snapshot(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


@dataclass
class SnapshotMetadata:
    """Everything a run's snapshot needs recorded alongside the raw
    binary dump -- per this milestone's own data-integrity requirement.
    `active_overlay`/`lba` are optional: filled in only when actually
    known, never guessed."""

    run_id: str
    snapshot_type: str  # "BEFORE" | "DURING" | "AFTER"
    path: str
    size: int
    sha256: str
    frame_number: int | None = None
    timestamp: float | None = None
    active_overlay: str | None = None
    save_slot: str | None = None
    scene_id: str | None = None
    lba: int | None = None

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id, "snapshot_type": self.snapshot_type, "path": self.path,
            "size": self.size, "sha256": self.sha256, "frame_number": self.frame_number,
            "timestamp": self.timestamp, "active_overlay": self.active_overlay,
            "save_slot": self.save_slot, "scene_id": self.scene_id, "lba": self.lba,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SnapshotMetadata":
        return cls(**d)


def build_snapshot_metadata(
    run_id: str,
    snapshot_type: str,
    path: str,
    data: bytes,
    **extra,
) -> SnapshotMetadata:
    return SnapshotMetadata(run_id=run_id, snapshot_type=snapshot_type, path=path, size=len(data), sha256=compute_sha256(data), **extra)


# --- diffing / clustering ---------------------------------------------------------


@dataclass
class ChangedRegion:
    start: int
    end: int  # exclusive
    changed_byte_count: int

    @property
    def size(self) -> int:
        return self.end - self.start

    @property
    def changed_fraction(self) -> float:
        return self.changed_byte_count / self.size if self.size else 0.0

    def to_dict(self) -> dict:
        return {"start": self.start, "end": self.end, "size": self.size, "changed_byte_count": self.changed_byte_count, "changed_fraction": self.changed_fraction}


def diff_regions(before: bytes, after: bytes, min_gap: int = 16) -> list[ChangedRegion]:
    """Finds every byte offset where `before` and `after` differ, then
    clusters them into contiguous regions -- two differing offsets less
    than `min_gap` bytes apart belong to the SAME region (real memory
    buffers rarely change byte-for-byte with zero untouched padding;
    requiring an exact contiguous run would fragment one real buffer
    into dozens of tiny "regions"). Never reports every changed byte
    independently, per this milestone's own instruction.

    Raises ValueError if the two buffers are different lengths (a
    real, likely-invalidating condition -- e.g. comparing snapshots
    from two different capture ranges -- never silently truncated)."""
    if len(before) != len(after):
        raise ValueError(f"snapshot length mismatch: before={len(before)} after={len(after)}")

    before_arr = np.frombuffer(before, dtype=np.uint8)
    after_arr = np.frombuffer(after, dtype=np.uint8)
    diff_positions = np.nonzero(before_arr != after_arr)[0]
    if diff_positions.size == 0:
        return []

    regions: list[ChangedRegion] = []
    region_start = int(diff_positions[0])
    region_last = region_start
    changed_count = 1
    for pos in diff_positions[1:]:
        pos = int(pos)
        if pos - region_last > min_gap:
            regions.append(ChangedRegion(region_start, region_last + 1, changed_count))
            region_start = pos
            changed_count = 0
        region_last = pos
        changed_count += 1
    regions.append(ChangedRegion(region_start, region_last + 1, changed_count))
    return regions


# --- region statistics -------------------------------------------------------------


def shannon_entropy(data: bytes) -> float:
    """0.0 (every byte identical) to 8.0 (uniform-random byte
    distribution) bits/byte -- a real, standard measure, never treated
    alone as "this is audio" (see score_candidate_region's own
    docstring for why)."""
    if not data:
        return 0.0
    counts = np.bincount(np.frombuffer(data, dtype=np.uint8), minlength=256)
    probs = counts[counts > 0] / len(data)
    return float(-np.sum(probs * np.log2(probs)))


def zero_density(data: bytes) -> float:
    if not data:
        return 0.0
    arr = np.frombuffer(data, dtype=np.uint8)
    return float(np.count_nonzero(arr == 0) / len(arr))


@dataclass
class RegionStats:
    region: ChangedRegion
    entropy_before: float
    entropy_during: float
    entropy_after: float
    zero_density_during: float
    alignment_4: bool  # start address is 4-byte aligned -- common for real buffers/structs
    stable_across_runs: bool = False  # filled in by cross-run correlation, not here

    def to_dict(self) -> dict:
        return {
            "region": self.region.to_dict(), "entropy_before": self.entropy_before,
            "entropy_during": self.entropy_during, "entropy_after": self.entropy_after,
            "zero_density_during": self.zero_density_during, "alignment_4": self.alignment_4,
            "stable_across_runs": self.stable_across_runs,
        }


def compute_region_stats(region: ChangedRegion, before: bytes, during: bytes, after: bytes) -> RegionStats:
    """`during` is compared at the SAME [start, end) slice as
    `before`/`after` were diffed at -- a caller comparing BEFORE-vs-
    DURING and DURING-vs-AFTER separately should pass the same region
    bounds to both calls; this function does not itself merge two
    different diff passes."""
    b = before[region.start:region.end]
    d = during[region.start:region.end]
    a = after[region.start:region.end]
    return RegionStats(
        region=region,
        entropy_before=shannon_entropy(b),
        entropy_during=shannon_entropy(d),
        entropy_after=shannon_entropy(a),
        zero_density_during=zero_density(d),
        alignment_4=(region.start % 4 == 0),
    )


# --- candidate scoring: multiple signals, never entropy alone --------------------


@dataclass
class CandidateScore:
    stats: RegionStats
    score: float
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"stats": self.stats.to_dict(), "score": self.score, "reasons": self.reasons}


# A real streaming/staging audio buffer on this hardware is typically
# at least a few hundred bytes (a handful of XA-ADPCM sectors' worth of
# payload, or several SPU ADPCM blocks) -- a 4-byte changed region is
# almost certainly an ordinary game-state counter, not an audio buffer.
MIN_PLAUSIBLE_AUDIO_REGION_SIZE = 256


def score_candidate_region(stats: RegionStats) -> CandidateScore:
    """Combines several independent signals into one score in [0, 1] --
    deliberately never "entropy alone," per this milestone's own
    explicit instruction (compressed non-audio game data is high
    entropy too; a real audio buffer should ALSO be larger than a
    handful of bytes, change substantially between BEFORE and DURING,
    and differ again between DURING and AFTER rather than staying
    frozen once written). Every contributing reason is recorded in
    `reasons`, not just the final number, so a human can see why a
    region ranked where it did."""
    reasons: list[str] = []
    score = 0.0

    if stats.region.size < MIN_PLAUSIBLE_AUDIO_REGION_SIZE:
        reasons.append(f"region size {stats.region.size} is below the plausible-audio-buffer floor ({MIN_PLAUSIBLE_AUDIO_REGION_SIZE})")
        return CandidateScore(stats, 0.0, reasons)

    size_score = min(1.0, stats.region.size / 4096.0)
    reasons.append(f"size={stats.region.size} bytes -> size_score={size_score:.2f}")
    score += 0.2 * size_score

    entropy_delta = abs(stats.entropy_during - stats.entropy_before)
    entropy_score = min(1.0, entropy_delta / 4.0)
    reasons.append(f"entropy before={stats.entropy_before:.2f} during={stats.entropy_during:.2f} (delta={entropy_delta:.2f}) -> {entropy_score:.2f}")
    score += 0.25 * entropy_score

    during_absolute_entropy_score = min(1.0, stats.entropy_during / 6.0)
    reasons.append(f"absolute during-entropy={stats.entropy_during:.2f} -> {during_absolute_entropy_score:.2f}")
    score += 0.15 * during_absolute_entropy_score

    changes_again_after = abs(stats.entropy_during - stats.entropy_after) > 0.3
    if changes_again_after:
        reasons.append("content differs again AFTER the line (not frozen once written) -- consistent with a reused/rotating buffer")
        score += 0.2
    else:
        reasons.append("content did not meaningfully change again after the line -- could still be a one-shot buffer, weaker evidence")

    low_zero_density_score = max(0.0, 1.0 - stats.zero_density_during * 2)
    reasons.append(f"zero-byte density during={stats.zero_density_during:.2f} -> {low_zero_density_score:.2f} (real audio data is rarely mostly zero)")
    score += 0.1 * low_zero_density_score

    if stats.alignment_4:
        reasons.append("region start is 4-byte aligned -- typical of a real allocated buffer/struct")
        score += 0.1
    else:
        reasons.append("region start is NOT 4-byte aligned -- weaker evidence of a deliberate buffer")

    if stats.stable_across_runs:
        reasons.append("this region (or its behavior) was reproducible across multiple runs -- strong evidence")
        score += 0.2

    return CandidateScore(stats, min(1.0, score), reasons)


def rank_candidate_regions(before: bytes, during: bytes, after: bytes, min_gap: int = 16) -> list[CandidateScore]:
    """The full Phase 2 pipeline for one run: diff BEFORE-vs-DURING to
    find candidate regions, score each one using both diffs (BEFORE/
    DURING/AFTER), sorted highest-score first."""
    regions = diff_regions(before, during, min_gap=min_gap)
    scored = [score_candidate_region(compute_region_stats(r, before, during, after)) for r in regions]
    scored.sort(key=lambda c: c.score, reverse=True)
    return scored


# --- cross-run correlation ---------------------------------------------------------


def mark_stable_across_runs(candidates_per_run: list[list[CandidateScore]], overlap_threshold: float = 0.5) -> None:
    """Mutates `stable_across_runs` in place on every CandidateScore's
    `.stats`, then the caller should re-score (score_candidate_region)
    if they want the score to reflect it -- kept as an explicit,
    separate step rather than baked into rank_candidate_regions, since
    "stable across runs" is only knowable once multiple runs exist,
    unlike every other signal which is knowable from one run alone."""
    if len(candidates_per_run) < 2:
        return
    for i, run_candidates in enumerate(candidates_per_run):
        for candidate in run_candidates:
            region = candidate.stats.region
            for j, other_run in enumerate(candidates_per_run):
                if i == j:
                    continue
                for other in other_run:
                    other_region = other.stats.region
                    overlap_lo = max(region.start, other_region.start)
                    overlap_hi = min(region.end, other_region.end)
                    overlap = max(0, overlap_hi - overlap_lo)
                    if overlap / region.size >= overlap_threshold:
                        candidate.stats.stable_across_runs = True
                        break


# --- audio-likeness heuristics: format hypotheses, never assumed in advance ------


class FormatHypothesis(str, Enum):
    SPU_ADPCM = "SPU_ADPCM"
    XA_ADPCM_LIKE = "XA_ADPCM_LIKE"
    PCM_S16 = "PCM_S16"
    PCM_U8 = "PCM_U8"
    UNKNOWN = "UNKNOWN"


@dataclass
class FormatGuess:
    hypothesis: FormatHypothesis
    confidence: float  # 0-1, a heuristic score, never a claim of certainty
    evidence: str


# psx-spx: SPU ADPCM blocks are 16 bytes -- byte 0 = (shift:4 | filter:4),
# byte 1 = flags, bytes 2-15 = 14 bytes of 4-bit ADPCM nibbles. Real PS1
# audio only ever uses filter indices 0-4 and shift values ~0-12; a
# random/non-audio byte stream will violate this far more often.
_SPU_ADPCM_BLOCK_SIZE = 16
_SPU_ADPCM_MAX_VALID_FILTER = 4
_SPU_ADPCM_MAX_VALID_SHIFT = 12
_SPU_ADPCM_VALID_FLAG_VALUES = {0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07}


def spu_adpcm_score(data: bytes) -> FormatGuess:
    """Heuristic only -- see module docstring. Scores the fraction of
    16-byte blocks whose header byte has a plausible filter/shift and
    whose flag byte is one of the documented values. Never claims a
    successful decode by itself; pair with an actual SPU-ADPCM decode
    attempt (out of scope for this module -- this project's own
    XA-ADPCM decoder in gcrts.xapack is a different, already-verified
    algorithm; SPU-internal ADPCM uses the same nibble/filter shape but
    a different block layout and is not implemented here yet)."""
    if len(data) < _SPU_ADPCM_BLOCK_SIZE:
        return FormatGuess(FormatHypothesis.UNKNOWN, 0.0, "region too small for even one SPU ADPCM block")
    block_count = len(data) // _SPU_ADPCM_BLOCK_SIZE
    plausible = 0
    for i in range(block_count):
        block = data[i * _SPU_ADPCM_BLOCK_SIZE:(i + 1) * _SPU_ADPCM_BLOCK_SIZE]
        header, flags = block[0], block[1]
        shift, filt = header >> 4, header & 0x0F
        if filt <= _SPU_ADPCM_MAX_VALID_FILTER and shift <= _SPU_ADPCM_MAX_VALID_SHIFT and flags in _SPU_ADPCM_VALID_FLAG_VALUES:
            plausible += 1
    fraction = plausible / block_count if block_count else 0.0
    return FormatGuess(
        FormatHypothesis.SPU_ADPCM if fraction > 0.6 else FormatHypothesis.UNKNOWN,
        fraction,
        f"{plausible}/{block_count} 16-byte blocks have a plausible SPU-ADPCM header/flag byte",
    )


def xa_adpcm_like_score(data: bytes) -> FormatGuess:
    """Heuristic for XA-ADPCM PAYLOAD fragments copied into RAM without
    their original 2352-byte sector framing (a RAM staging buffer would
    plausibly hold just the 2304-byte payload, or even smaller
    fragments, not full raw sectors) -- reuses this project's own
    already-verified ADPCM group shape (gcrts.xapack): each 128-byte
    group holds 4 header bytes pairs at a fixed position followed by
    ADPCM nibble data. Checks the group-header byte pattern's
    plausibility (each header byte's low nibble is a filter/shift pair
    with the same valid-range constraint as SPU ADPCM, since XA-ADPCM
    shares the same underlying nibble/filter shape per psx-spx)."""
    from gcrts.xapack import XA_ADPCM_PAYLOAD_SIZE

    group_size = 128
    if len(data) < group_size:
        return FormatGuess(FormatHypothesis.UNKNOWN, 0.0, "region too small for even one XA-ADPCM group")
    group_count = len(data) // group_size
    plausible = 0
    for i in range(group_count):
        group = data[i * group_size:(i + 1) * group_size]
        headers = group[4:12]  # 4 header byte PAIRS, per gcrts.xapack's own verified layout
        ok = True
        for h in headers:
            shift, filt = h >> 4, h & 0x0F
            if filt > _SPU_ADPCM_MAX_VALID_FILTER or shift > _SPU_ADPCM_MAX_VALID_SHIFT:
                ok = False
                break
        if ok:
            plausible += 1
    fraction = plausible / group_count if group_count else 0.0
    evidence = f"{plausible}/{group_count} 128-byte ADPCM groups have plausible header bytes (payload size reference: {XA_ADPCM_PAYLOAD_SIZE} bytes/sector)"
    return FormatGuess(FormatHypothesis.XA_ADPCM_LIKE if fraction > 0.6 else FormatHypothesis.UNKNOWN, fraction, evidence)


def pcm_heuristic_score(data: bytes) -> FormatGuess:
    """Tests signed-16-bit PCM plausibility only (the far more common
    PS1 in-RAM decoded-audio representation) -- a real speech/audio
    signal's sample-to-sample deltas cluster far more tightly than
    white noise's, and its byte-level distribution is far from uniform
    (unlike compressed/high-entropy non-audio data). Heuristic only --
    never overfits by itself; a genuinely random region can still score
    moderately, so this is one signal among several, not a verdict."""
    if len(data) < 4 or len(data) % 2 != 0:
        return FormatGuess(FormatHypothesis.UNKNOWN, 0.0, "region size not compatible with 16-bit PCM framing")
    samples = np.frombuffer(data, dtype="<i2").astype(np.float64)
    if len(samples) < 2:
        return FormatGuess(FormatHypothesis.UNKNOWN, 0.0, "too few samples")
    deltas = np.abs(np.diff(samples))
    mean_abs = np.mean(np.abs(samples)) or 1.0
    smoothness = 1.0 - min(1.0, float(np.mean(deltas)) / (mean_abs + 1.0))
    nonzero_fraction = float(np.count_nonzero(samples)) / len(samples)
    confidence = max(0.0, min(1.0, 0.6 * smoothness + 0.4 * nonzero_fraction))
    return FormatGuess(
        FormatHypothesis.PCM_S16 if confidence > 0.5 else FormatHypothesis.UNKNOWN,
        confidence,
        f"sample-to-sample smoothness={smoothness:.2f}, nonzero_fraction={nonzero_fraction:.2f}",
    )


def classify_audio_likeness(data: bytes) -> list[FormatGuess]:
    """Runs every heuristic (never assuming a format in advance) and
    returns all of them, highest confidence first -- the caller decides
    what confidence bar counts as "worth extracting," this function
    does not gate that itself."""
    guesses = [spu_adpcm_score(data), xa_adpcm_like_score(data), pcm_heuristic_score(data)]
    guesses.sort(key=lambda g: g.confidence, reverse=True)
    return guesses


# --- candidate extraction ----------------------------------------------------------


def extract_candidate_pcm_s16(data: bytes) -> tuple[int, bytes]:
    """The only extraction path implemented so far: treats `data` as
    raw signed-16-bit mono PCM at the PS1's standard XA sample rate
    (37800 Hz) -- the same rate this project's own XA-ADPCM decoder
    already established for every real audio asset on this disc
    (gcrts.xapack). Returns (sample_rate, pcm_bytes) ready for
    gcrts.xapack.write_wav. SPU-ADPCM/XA-like candidates are NOT
    decoded here yet -- flagged as the natural next step once a
    reproducible candidate region of that hypothesis actually exists
    (see module docstring: extraction should follow real evidence, not
    precede it)."""
    return 37800, data


# --- CLI ---------------------------------------------------------------------------


def _print_candidate(rank: int, candidate: CandidateScore, before: bytes, during: bytes) -> None:
    r = candidate.stats.region
    print(f"#{rank}: 0x{r.start:06X}-0x{r.end:06X} ({r.size} bytes, {candidate.stats.region.changed_fraction:.0%} changed) -- score={candidate.score:.2f}")
    for reason in candidate.reasons:
        print(f"    - {reason}")
    guesses = classify_audio_likeness(during[r.start:r.end])
    print("    audio-likeness: " + ", ".join(f"{g.hypothesis.value}={g.confidence:.2f}" for g in guesses))


def _cmd_diff(args) -> int:
    before = load_snapshot(args.before)
    during = load_snapshot(args.during)
    after = load_snapshot(args.after)
    candidates = rank_candidate_regions(before, during, after)
    print(f"{len(candidates)} candidate region(s) found (BEFORE vs DURING, min_gap={args.min_gap}):\n")
    for i, c in enumerate(candidates[: args.top], start=1):
        _print_candidate(i, c, before, during)
        print()
    return 0


def _cmd_analyze_run(args) -> int:
    import os

    run_dir = args.run_dir
    before_path = os.path.join(run_dir, "before.bin")
    during_path = os.path.join(run_dir, "during.bin")
    after_path = os.path.join(run_dir, "after.bin")
    for p in (before_path, during_path, after_path):
        if not os.path.exists(p):
            print(f"missing expected snapshot: {p}")
            return 1
    before, during, after = load_snapshot(before_path), load_snapshot(during_path), load_snapshot(after_path)
    candidates = rank_candidate_regions(before, during, after)
    print(f"{run_dir}: {len(candidates)} candidate region(s)\n")
    for i, c in enumerate(candidates[: args.top], start=1):
        _print_candidate(i, c, before, during)
        print()
    return 0


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Audio Data Trace: offline RAM-snapshot diff/scoring/audio-likeness analysis.")
    sub = parser.add_subparsers(dest="command", required=True)

    diff_parser = sub.add_parser("diff", help="Diff and rank candidate regions across three snapshots.")
    diff_parser.add_argument("before")
    diff_parser.add_argument("during")
    diff_parser.add_argument("after")
    diff_parser.add_argument("--min-gap", type=int, default=16, dest="min_gap")
    diff_parser.add_argument("--top", type=int, default=10)
    diff_parser.set_defaults(func=_cmd_diff)

    run_parser = sub.add_parser("analyze-run", help="Analyze a run directory containing before.bin/during.bin/after.bin.")
    run_parser.add_argument("run_dir")
    run_parser.add_argument("--top", type=int, default=10)
    run_parser.set_defaults(func=_cmd_analyze_run)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    import sys

    sys.exit(main())
