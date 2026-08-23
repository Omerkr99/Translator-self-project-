import numpy as np
import pytest

from gcrts.audio_data_trace import (
    ChangedRegion,
    FormatHypothesis,
    MIN_PLAUSIBLE_AUDIO_REGION_SIZE,
    RegionStats,
    build_snapshot_metadata,
    classify_audio_likeness,
    compute_region_stats,
    compute_sha256,
    diff_regions,
    extract_candidate_pcm_s16,
    load_snapshot,
    mark_stable_across_runs,
    pcm_heuristic_score,
    rank_candidate_regions,
    score_candidate_region,
    shannon_entropy,
    spu_adpcm_score,
    xa_adpcm_like_score,
    zero_density,
)


# --- snapshot loading / metadata ------------------------------------------------


def test_load_snapshot_round_trips(tmp_path):
    path = str(tmp_path / "snap.bin")
    data = bytes(range(256)) * 4
    with open(path, "wb") as f:
        f.write(data)
    assert load_snapshot(path) == data


def test_compute_sha256_matches_known_value():
    assert compute_sha256(b"") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"[:64]


def test_build_snapshot_metadata_computes_size_and_hash():
    data = b"\x01\x02\x03\x04"
    meta = build_snapshot_metadata("run01", "BEFORE", "run01_before.bin", data, save_slot="9", scene_id="target_line")
    assert meta.size == 4
    assert meta.sha256 == compute_sha256(data)
    assert meta.save_slot == "9"
    assert meta.scene_id == "target_line"
    assert meta.active_overlay is None  # never guessed


def test_snapshot_metadata_round_trips_dict():
    meta = build_snapshot_metadata("run01", "DURING", "p.bin", b"abc", lba=12345)
    restored = meta.from_dict(meta.to_dict())
    assert restored == meta


# --- diff_regions ----------------------------------------------------------------


def test_diff_regions_no_changes():
    data = bytes(1000)
    assert diff_regions(data, data) == []


def test_diff_regions_single_contiguous_region():
    before = bytearray(1000)
    after = bytearray(before)
    for i in range(100, 200):
        after[i] = 0xFF
    regions = diff_regions(bytes(before), bytes(after))
    assert len(regions) == 1
    assert regions[0].start == 100
    assert regions[0].end == 200
    assert regions[0].changed_byte_count == 100


def test_diff_regions_merges_nearby_gaps():
    before = bytearray(1000)
    after = bytearray(before)
    after[100] = 1
    after[110] = 1  # 10 bytes away -- within default min_gap=16, should merge into one region
    regions = diff_regions(bytes(before), bytes(after))
    assert len(regions) == 1
    assert regions[0].start == 100
    assert regions[0].end == 111


def test_diff_regions_splits_on_large_gaps():
    before = bytearray(1000)
    after = bytearray(before)
    after[100] = 1
    after[500] = 1  # far apart -- must be 2 separate regions
    regions = diff_regions(bytes(before), bytes(after))
    assert len(regions) == 2


def test_diff_regions_rejects_length_mismatch():
    with pytest.raises(ValueError):
        diff_regions(b"\x00" * 10, b"\x00" * 20)


def test_changed_region_fraction_and_size():
    r = ChangedRegion(start=100, end=200, changed_byte_count=50)
    assert r.size == 100
    assert r.changed_fraction == 0.5


# --- entropy / zero density -------------------------------------------------------


def test_shannon_entropy_all_same_byte_is_zero():
    assert shannon_entropy(b"\x00" * 1000) == pytest.approx(0.0)


def test_shannon_entropy_uniform_bytes_is_near_max():
    data = bytes(range(256)) * 10
    assert shannon_entropy(data) == pytest.approx(8.0, abs=0.01)


def test_shannon_entropy_empty_is_zero():
    assert shannon_entropy(b"") == 0.0


def test_zero_density_all_zero():
    assert zero_density(b"\x00" * 100) == 1.0


def test_zero_density_no_zero():
    assert zero_density(b"\x01" * 100) == 0.0


# --- region stats / scoring --------------------------------------------------------


def _region_stats(size=1024, entropy_before=1.0, entropy_during=6.0, entropy_after=1.0, zero_density_during=0.05, alignment_4=True, stable=False):
    return RegionStats(
        region=ChangedRegion(0, size, size),
        entropy_before=entropy_before, entropy_during=entropy_during, entropy_after=entropy_after,
        zero_density_during=zero_density_during, alignment_4=alignment_4, stable_across_runs=stable,
    )


def test_compute_region_stats_real_slices():
    before = bytes(1000)
    during = bytes([1] * 1000)
    after = bytes(1000)
    region = ChangedRegion(100, 300, 200)
    stats = compute_region_stats(region, before, during, after)
    assert stats.entropy_before == 0.0
    assert stats.entropy_during == 0.0  # all-same-byte (0x01) is still zero entropy
    assert stats.alignment_4 is True  # 100 % 4 == 0


def test_score_below_minimum_size_is_zero():
    stats = _region_stats(size=MIN_PLAUSIBLE_AUDIO_REGION_SIZE - 1)
    result = score_candidate_region(stats)
    assert result.score == 0.0
    assert "below the plausible-audio-buffer floor" in result.reasons[0]


def test_score_rewards_entropy_increase_and_size():
    low = score_candidate_region(_region_stats(entropy_before=1.0, entropy_during=1.0)).score
    high = score_candidate_region(_region_stats(entropy_before=1.0, entropy_during=6.0)).score
    assert high > low


def test_score_rewards_stability_across_runs():
    unstable = score_candidate_region(_region_stats(stable=False)).score
    stable = score_candidate_region(_region_stats(stable=True)).score
    assert stable > unstable


def test_score_penalizes_high_zero_density():
    sparse = score_candidate_region(_region_stats(zero_density_during=0.9)).score
    dense = score_candidate_region(_region_stats(zero_density_during=0.05)).score
    assert dense > sparse


def test_score_never_entropy_alone_a_frozen_region_scores_lower_than_a_changing_one():
    """Explicit regression for this milestone's own instruction: high
    entropy alone must not be sufficient. A region with high DURING
    entropy that stays frozen (same entropy AFTER) should score lower
    than one that also changes again after -- i.e. multiple signals
    combine, not just the absolute entropy value."""
    frozen = score_candidate_region(_region_stats(entropy_during=6.0, entropy_after=6.0001)).score
    changes_again = score_candidate_region(_region_stats(entropy_during=6.0, entropy_after=1.0)).score
    assert changes_again > frozen


def test_rank_candidate_regions_sorted_highest_first():
    before = bytearray(4000)
    during = bytearray(before)
    for i in range(500, 1500):
        during[i] = (i * 7) % 256  # big, high-entropy region
    for i in range(2000, 2010):
        during[i] = 1  # tiny region, below the size floor
    after = bytes(before)
    scores = rank_candidate_regions(bytes(before), bytes(during), after)
    assert len(scores) == 2
    assert scores[0].score >= scores[1].score
    assert scores[0].stats.region.size == 1000


# --- cross-run correlation -------------------------------------------------------


def test_mark_stable_across_runs_flags_overlapping_regions():
    run1 = [score_candidate_region(_region_stats())]
    run1[0].stats.region = ChangedRegion(1000, 2000, 1000)
    run2 = [score_candidate_region(_region_stats())]
    run2[0].stats.region = ChangedRegion(1000, 2000, 1000)  # identical region in another run
    mark_stable_across_runs([run1, run2])
    assert run1[0].stats.stable_across_runs is True
    assert run2[0].stats.stable_across_runs is True


def test_mark_stable_across_runs_does_not_flag_unrelated_regions():
    run1 = [score_candidate_region(_region_stats())]
    run1[0].stats.region = ChangedRegion(1000, 2000, 1000)
    run2 = [score_candidate_region(_region_stats())]
    run2[0].stats.region = ChangedRegion(50000, 51000, 1000)  # nowhere near run1's region
    mark_stable_across_runs([run1, run2])
    assert run1[0].stats.stable_across_runs is False


def test_mark_stable_across_runs_single_run_is_a_no_op():
    run1 = [score_candidate_region(_region_stats())]
    mark_stable_across_runs([run1])
    assert run1[0].stats.stable_across_runs is False


# --- format heuristics -------------------------------------------------------------


def test_spu_adpcm_score_plausible_blocks():
    # header byte: shift=2, filter=1 (both in-range); flag byte 0x00 (valid)
    block = bytes([0x21, 0x00]) + bytes(14)
    data = block * 20
    guess = spu_adpcm_score(data)
    assert guess.confidence > 0.9
    assert guess.hypothesis == FormatHypothesis.SPU_ADPCM


def test_spu_adpcm_score_implausible_blocks():
    # header byte: shift=15, filter=15 -- both out of valid range
    block = bytes([0xFF, 0xFF]) + bytes(14)
    data = block * 20
    guess = spu_adpcm_score(data)
    assert guess.confidence < 0.5
    assert guess.hypothesis == FormatHypothesis.UNKNOWN


def test_spu_adpcm_score_too_small():
    guess = spu_adpcm_score(b"\x00" * 4)
    assert guess.confidence == 0.0


def test_xa_adpcm_like_score_plausible_groups():
    header_pair = bytes([0x21, 0x21, 0x21, 0x21])
    group = bytes(4) + header_pair * 2 + bytes(128 - 4 - 8)
    data = group * 5
    guess = xa_adpcm_like_score(data)
    assert guess.confidence > 0.9


def test_xa_adpcm_like_score_too_small():
    guess = xa_adpcm_like_score(b"\x00" * 10)
    assert guess.confidence == 0.0


def test_pcm_heuristic_score_smooth_signal():
    t = np.linspace(0, 1, 4000)
    signal = (np.sin(2 * np.pi * 220 * t) * 20000).astype("<i2").tobytes()
    guess = pcm_heuristic_score(signal)
    assert guess.confidence > 0.5
    assert guess.hypothesis == FormatHypothesis.PCM_S16


def test_pcm_heuristic_score_odd_length_rejected():
    guess = pcm_heuristic_score(b"\x00" * 7)
    assert guess.hypothesis == FormatHypothesis.UNKNOWN
    assert guess.confidence == 0.0


def test_classify_audio_likeness_returns_sorted_guesses():
    t = np.linspace(0, 1, 4000)
    signal = (np.sin(2 * np.pi * 220 * t) * 20000).astype("<i2").tobytes()
    guesses = classify_audio_likeness(signal)
    assert len(guesses) == 3
    assert guesses[0].confidence >= guesses[1].confidence >= guesses[2].confidence


# --- candidate extraction ----------------------------------------------------------


def test_extract_candidate_pcm_s16_returns_xa_sample_rate():
    sample_rate, pcm = extract_candidate_pcm_s16(b"\x00\x01" * 100)
    assert sample_rate == 37800
    assert pcm == b"\x00\x01" * 100
