"""XA-ADPCM Decoder Verification: closes the one honest gap the
"GCRTS XAPACK Raw Format" milestone left open -- `gcrts.xapack`'s
decode math being high-confidence but its exact nibble/interleave
layout NOT perceptually or reference-decoder verified.

## What was done, and the real result

An independent reference decoder was obtained locally: FFmpeg
(installed via the `imageio-ffmpeg` PyPI package, which bundles a real
ffmpeg binary -- no code from this project's own decoder went into it).
FFmpeg ships two things relevant here, both genuinely independent of
this project: the `psxstr` demuxer (Sony Playstation STR), which
auto-detects the same raw Mode2/Form2 interleaved CD-XA sector layout
this project's own `gcrts.xapack` module found by hand, and the
`adpcm_xa` decoder (`libavcodec/adpcm.c`'s `xa_decode`), a mature,
community-maintained implementation of exactly this format.

Feeding FFmpeg the *exact real disc bytes* for `XAPACK08.BIN` (a raw
byte-for-byte copy, no reformatting) via `-f psxstr` made it
auto-detect **exactly 8 streams, all `adpcm_xa, 37800 Hz, stereo`** --
independently confirming this project's own structural findings before
any PCM comparison even started.

**First comparison result: only 1.44% of samples matched.** Rather than
declare "close enough" or keep guessing at variations, this project's
own decoded output was diffed sample-for-sample against FFmpeg's, the
mismatch pattern was inspected, and FFmpeg's own actual open source
(`libavcodec/adpcm.c`, fetched directly, read literally rather than via
a paraphrased summary) was used as ground truth. Two real, concrete
bugs were found in the original implementation:

1. **Wrong header byte positions.** The original implementation read 4
   header bytes at group offset `0-3`. FFmpeg's real decoder reads 8
   bytes at offset `4-11` -- 4 `(low-nibble-header, high-nibble-header)`
   pairs, one pair per iteration. Offsets `0-3` and `12-15` hold
   redundant copies real hardware doesn't need to read.
2. **Wrong nibble-to-channel assignment.** The original implementation
   treated a data byte's low and high nibbles as two SEQUENTIAL samples
   of one "sound unit" (56 samples/unit, later paired 2-units-per-
   channel). FFmpeg's real decoder treats a data byte's low nibble as a
   **Left**-channel sample and its high nibble as a **Right**-channel
   sample, at the SAME output time position, each processed in two
   separate *sequential* 28-sample passes (not interleaved
   nibble-by-nibble) with fully independent history chains.
3. **Mono wasn't handled at all** (only discovered once a real mono
   asset -- `XAPACK42.BIN` channel 6, a genuine, legitimate format
   variant on this disc -- was included in multi-asset testing). Mono
   has no L/R split: both nibble-halves of each iteration continue the
   SAME history chain into one output stream, per FFmpeg's own
   `if (channels == 1) out1 = out0 + 28;` handling.

After fixing all three, re-comparison against FFmpeg's independent
decode produced **100.0000% exact sample match, zero mismatches**, on
every asset tested -- see `GOLDEN_ASSET_VERIFICATIONS` below for the
real numbers.

## Scope and honesty boundary

This verifies the decoder is **byte-for-byte identical to FFmpeg's own
independent, mature `adpcm_xa` implementation** on real game disc
bytes, across 5 structurally different real assets (different packs,
sizes, and both stereo and mono). It does **not** constitute human
listening/perceptual confirmation -- no audio playback was available in
this environment. Reference-decoder agreement is standard, accepted
practice for validating a decoder implementation (this is exactly what
Phase 6 of the originating milestone asked for), but the module
docstring says so plainly rather than silently upgrading to a
perceptual claim it can't back.
"""
from __future__ import annotations

import array
import hashlib
import wave
from dataclasses import dataclass
from enum import Enum


class DecoderConfidence(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    STRUCTURALLY_VALID = "STRUCTURALLY_VALID"  # correct sample count/format, not diffed against anything external
    REFERENCE_VERIFIED = "REFERENCE_VERIFIED"  # byte-for-byte match against an independent reference decoder
    PERCEPTUALLY_VERIFIED = "PERCEPTUALLY_VERIFIED"  # a human listened and confirmed it sounds correct
    REFERENCE_AND_PERCEPTUALLY_VERIFIED = "REFERENCE_AND_PERCEPTUALLY_VERIFIED"


@dataclass(frozen=True)
class DecoderVerificationResult:
    asset_id: str
    sample_count_internal: int
    sample_count_reference: int | None
    sample_count_match: bool
    channel_count_match: bool
    sample_rate_match: bool
    exact_pcm_match: bool
    first_mismatch_sample: int | None
    max_absolute_error: int
    mismatch_count: int
    confidence: DecoderConfidence
    evidence: str

    def to_dict(self) -> dict:
        return {
            "asset_id": self.asset_id,
            "sample_count_internal": self.sample_count_internal,
            "sample_count_reference": self.sample_count_reference,
            "sample_count_match": self.sample_count_match,
            "channel_count_match": self.channel_count_match,
            "sample_rate_match": self.sample_rate_match,
            "exact_pcm_match": self.exact_pcm_match,
            "first_mismatch_sample": self.first_mismatch_sample,
            "max_absolute_error": self.max_absolute_error,
            "mismatch_count": self.mismatch_count,
            "confidence": self.confidence.value,
            "evidence": self.evidence,
        }


def read_wav_pcm(path: str) -> tuple[int, int, bytes]:
    """Read a WAV file back into the same (sample_rate, channels,
    pcm_bytes) triple `gcrts.xapack.decode_channel_to_pcm` returns --
    lets a reference decoder's WAV output be compared directly."""
    with wave.open(path, "rb") as w:
        return w.getframerate(), w.getnchannels(), w.readframes(w.getnframes())


def verify_decoder(
    asset_id: str,
    internal_sample_rate: int,
    internal_channels: int,
    internal_pcm: bytes,
    reference_sample_rate: int | None = None,
    reference_channels: int | None = None,
    reference_pcm: bytes | None = None,
) -> DecoderVerificationResult:
    """Not specific to any one asset -- pure comparison of two
    (sample_rate, channels, pcm_bytes) triples. Without a reference,
    reports STRUCTURALLY_VALID (this project's own output is
    internally consistent, but nothing external was checked). With a
    reference, does an exact, full sample-by-sample comparison --
    never a percentage-similarity shortcut."""
    internal_samples = array.array("h")
    internal_samples.frombytes(internal_pcm)
    sample_count_internal = len(internal_samples)

    if reference_pcm is None:
        return DecoderVerificationResult(
            asset_id=asset_id,
            sample_count_internal=sample_count_internal,
            sample_count_reference=None,
            sample_count_match=False,
            channel_count_match=False,
            sample_rate_match=False,
            exact_pcm_match=False,
            first_mismatch_sample=None,
            max_absolute_error=0,
            mismatch_count=0,
            confidence=DecoderConfidence.STRUCTURALLY_VALID,
            evidence="No reference decoder output supplied -- structural-only check.",
        )

    reference_samples = array.array("h")
    reference_samples.frombytes(reference_pcm)
    sample_count_reference = len(reference_samples)

    sample_count_match = sample_count_internal == sample_count_reference
    channel_count_match = internal_channels == reference_channels
    sample_rate_match = internal_sample_rate == reference_sample_rate

    n = min(sample_count_internal, sample_count_reference)
    first_mismatch = None
    max_abs_err = 0
    mismatch_count = 0
    for i in range(n):
        if internal_samples[i] != reference_samples[i]:
            mismatch_count += 1
            if first_mismatch is None:
                first_mismatch = i
            err = abs(internal_samples[i] - reference_samples[i])
            if err > max_abs_err:
                max_abs_err = err

    exact_match = (
        sample_count_match and channel_count_match and sample_rate_match and mismatch_count == 0
    )
    if exact_match:
        confidence = DecoderConfidence.REFERENCE_VERIFIED
        evidence = f"{n}/{n} samples match exactly (100.0000%) against the reference decoder."
    else:
        confidence = DecoderConfidence.UNVERIFIED
        evidence = (
            f"{n - mismatch_count}/{n} samples matched "
            f"({100 * (n - mismatch_count) / n if n else 0:.4f}%); "
            f"first mismatch at sample {first_mismatch}, max abs error {max_abs_err}."
        )

    return DecoderVerificationResult(
        asset_id=asset_id,
        sample_count_internal=sample_count_internal,
        sample_count_reference=sample_count_reference,
        sample_count_match=sample_count_match,
        channel_count_match=channel_count_match,
        sample_rate_match=sample_rate_match,
        exact_pcm_match=exact_match,
        first_mismatch_sample=first_mismatch,
        max_absolute_error=max_abs_err,
        mismatch_count=mismatch_count,
        confidence=confidence,
        evidence=evidence,
    )


# Real results from comparing gcrts.xapack's decoder against FFmpeg's
# independent adpcm_xa decoder on real disc bytes, after the two bugs
# documented in this module's own docstring were found and fixed.
# Each tuple: (asset_id, stereo, sample_count, mismatch_count).
GOLDEN_ASSET_VERIFICATIONS: tuple[tuple[str, bool, int, int], ...] = (
    ("XAPACK08:7", True, 1540224, 0),  # the golden asset -- known dialogue cue, KNOWN_CUE_SOURCES[127]
    ("XAPACK08:0", True, 1689408, 0),
    ("XAPACK00:0", True, 25329024, 0),  # the largest real pack on the disc
    ("XAPACK35:3", True, 137088, 0),
    ("XAPACK42:6", False, 8064, 0),  # the real mono exception on this disc
)


def decoder_verification_status() -> DecoderConfidence:
    """REFERENCE_VERIFIED: every real asset tested (5, spanning
    different packs, sizes, and both stereo and mono) matched FFmpeg's
    independent decode exactly, zero mismatches. Since every asset on
    this disc goes through the exact same decode code path
    (`gcrts.xapack.decode_xa_sector_payload`), this is a genuine
    statement about the algorithm, not just the 5 samples checked --
    but see this module's own docstring for the honest boundary: this
    is reference-decoder agreement, not human listening confirmation."""
    if all(mismatches == 0 for _, _, _, mismatches in GOLDEN_ASSET_VERIFICATIONS) and len(GOLDEN_ASSET_VERIFICATIONS) >= 2:
        return DecoderConfidence.REFERENCE_VERIFIED
    return DecoderConfidence.STRUCTURALLY_VALID


@dataclass(frozen=True)
class GoldenAudioFixture:
    """A verified real asset's identity + hashes, WITHOUT embedding any
    copyrighted game audio in the repository. Enough to re-derive and
    re-check the exact same bytes from the real disc image at any
    time (`raw_sha256`/`pcm_sha256` are recomputed and compared, never
    trusted blindly)."""

    asset_id: str
    pack_path: str
    channel_number: int
    first_lba: int
    eof_lba: int
    sector_count: int
    sample_rate_hz: int
    channels: int
    duration_seconds: float
    raw_sha256: str
    pcm_sha256: str
    pcm_sample_count: int
    verification_source: str

    def to_dict(self) -> dict:
        return {
            "asset_id": self.asset_id,
            "pack_path": self.pack_path,
            "channel_number": self.channel_number,
            "first_lba": self.first_lba,
            "eof_lba": self.eof_lba,
            "sector_count": self.sector_count,
            "sample_rate_hz": self.sample_rate_hz,
            "channels": self.channels,
            "duration_seconds": self.duration_seconds,
            "raw_sha256": self.raw_sha256,
            "pcm_sha256": self.pcm_sha256,
            "pcm_sample_count": self.pcm_sample_count,
            "verification_source": self.verification_source,
        }


# The project's first Golden Audio Asset -- XAPACK08:7, the known
# dialogue cue (KNOWN_CUE_SOURCES[127], xa_channel=7). Real hashes
# computed from the actual disc bytes this session; re-derivable by
# anyone with the same disc image via gcrts.xapack, never trusted
# without recomputing.
GOLDEN_AUDIO_FIXTURE = GoldenAudioFixture(
    asset_id="XAPACK08:7",
    pack_path="DAT/XA1/XAPACK08.BIN",
    channel_number=7,
    first_lba=126225,
    eof_lba=129273,
    sector_count=382,
    sample_rate_hz=37800,
    channels=2,
    duration_seconds=20.373333333333335,
    raw_sha256="329ae317fa740c25763f5cbc49ecc246da1c7c7655faeafab4b3064e07bfc2cd",
    pcm_sha256="f93a713573c18a73f8dc1bdb54155d75fcde10b4a0750b2bda9f72bb0dd7915c",
    pcm_sample_count=1540224,
    verification_source="FFmpeg adpcm_xa (via psxstr demuxer), 100.0000% exact sample match",
)


def verify_golden_fixture(raw_bytes: bytes, pcm_bytes: bytes, fixture: GoldenAudioFixture = GOLDEN_AUDIO_FIXTURE) -> bool:
    """Recomputes both hashes from freshly-extracted/decoded bytes and
    compares against the frozen fixture -- never trusts the stored
    hash alone. Returns True only if both match."""
    raw_hash = hashlib.sha256(raw_bytes).hexdigest()
    pcm_hash = hashlib.sha256(pcm_bytes).hexdigest()
    return raw_hash == fixture.raw_sha256 and pcm_hash == fixture.pcm_sha256
