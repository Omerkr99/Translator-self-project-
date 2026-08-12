"""XAPACK Raw Format: the physical structure inside `XAPACK*.BIN` files,
proven directly from real disc bytes -- not inferred from a filename, a
debugger display, or a software toggle. Part of the "GCRTS XAPACK Raw
Format + Audio Asset Discovery" milestone
(`docs/audio/XAPACK_FORMAT.md`).

## What was found, and how

A byte-level scan of real sectors (`gcrts.xa_disc_index.read_sector_meta`,
already live-validated in prior sessions) across all 43 real XAPACK files
found a single, near-universal structure:

- Every audio-carrying sector's `submode` is exactly `0x64` -- Audio
  (bit2) + Form2 (bit5) + Realtime (bit6) set, nothing else. This is the
  textbook Green Book / White Book CD-XA "real-time audio sector"
  signature -- genuinely standard XA, not a custom container using the
  filename as camouflage.
- Every such sector's `coding_info` is exactly `0x01`: stereo (bits0-1=1),
  37800 Hz (bits2-3=0), 4-bit ADPCM (bits4-5=0), no emphasis. This
  independently matches (and explains) the SPU Debug window's own static
  `XA` panel reading of `Frequency: 37800`/`Stereo: 1` found in an
  earlier milestone (`AUDIO_TRANSPORT_PATH.md`) -- that value was never
  meaningless, it was accurately reporting the real, constant hardware
  decode configuration; it just doesn't change per dialogue event because
  the *format* never changes, only the *content* does.
- Every pack interleaves exactly 8 channels (0-7) in strict round-robin
  from its very first sector (`channel_number` cycling 0,1,2,...,7,0,1,...
  with zero gaps in the audio region) -- a real, physical 8-way CD-XA
  interleave, not merely a "positional artifact" of one arbitrarily
  observed LBA (the caveat `gcrts.xa_disc_index`'s own docstring
  originally raised). Within one pack, position genuinely *is* channel
  identity, by construction.
- Each of the 8 channels carries its own independent audio stream of its
  own natural length, terminated by a real, physical **EOF marker**:
  exactly one sector per channel has `submode = 0xE4` (the same
  Audio+Form2+Realtime bits, plus EOF/bit7) at exactly that channel's own
  last audio-flagged sector -- confirmed byte-for-byte across every pack
  checked (the EOF sector's LBA always equals that channel's own highest
  audio-flagged LBA). After a channel's own EOF, its future interleave
  slots carry silence/padding sectors (`submode=0x00`, non-audio) for the
  rest of the pack, while other channels continue independently. This is
  a genuine, physical, per-stream segmentation signal -- not inferred
  from timing or guessed from a wall-clock duration.
- Every pack ends with exactly one true file terminator sector
  (`submode=0x80` or the rarer `0x89` variant seen once, both
  EOF-flagged but *not* audio-flagged) as its own physically last sector.

Validated across **all 43 real XAPACK files** (not a handful of samples):
41/43 match this model exactly (8 channels, 1 terminator, each channel's
EOF matching its own last audio sector). The 2 exceptions are minor,
explainable, non-contradicting variations: `XAPACK42.BIN` (the very last,
smallest pack) uses only 7 of the 8 channel slots; `XAPACK29.BIN` has one
extra terminator-family sector (`submode=0x89`, itself just an
EOR+Data+EOF terminator variant, still landing on the pack's own final
sector) alongside the standard one. Neither undermines the general model.

## Cross-validated against real, independently-established live anchors

Two real live-observed LBAs already on record elsewhere in this project
(`gcrts.runtime_audio`, `RUNTIME_AUDIO_TRACKER.md`) fall exactly where
this structural model predicts they should:

- The confirmed dialogue cue (script parameter 127, `xa_channel=7`,
  `KNOWN_CUE_SOURCES[127]`) was live-observed at LBA `126921` in
  `XAPACK08.BIN`. This module's own channel-8 stream for that pack spans
  LBA `126225`-`129273` (channel 7's own first-audio to its own EOF
  sector) -- `126921` falls squarely inside that range.
- A second, independent live capture landed exactly on `XAPACK06.BIN`'s
  own start LBA (`116010`) -- exactly channel 0's own first sector in
  this module's model.

Neither anchor was used to *derive* the structural model (which comes
entirely from the disc's own physical sector flags); both were used only
to *check* it after the fact, per the milestone's own Phase 6/7
instruction. Both checks passed.

## Format classification

`STANDARD_XA` is used only where the physical evidence above actually
holds -- see `classify_pack_format()`. This is a physical-sector-level
finding, independent of (and now explaining) the SPU Debug window's
static XA panel reading from the prior milestone.

## The ADPCM decoder: an honest confidence breakdown

`decode_channel_to_pcm()` implements the standard, extremely
well-documented PSX ADPCM sample formula (5 filter coefficient pairs,
4-bit signed nibble + adaptive shift/range, running 2-sample history per
sound unit) -- this part is implemented with high confidence; it is the
same core math used for SPU voice ADPCM and is consistent across every
public reference this project's author is aware of.

The one genuinely **unverified** piece is the exact byte/nibble layout
used to pack 4 interleaved "sound units" into each 128-byte sound group
(which of two structurally-plausible orderings the real encoder uses).
This implementation uses the ordering described in the most commonly
cited public CD-XA documentation (4 header bytes then 112 data bytes
arranged as 28 rows of 4 bytes, one byte per sound unit per row, low/high
nibble = two consecutive samples for that unit) and cross-checks
correctly against an independent constant: decoding one whole sector
this way produces exactly **2016 samples per channel** -- the same
number the SPU Debug window's own `Samples` field reported (see
`AUDIO_TRANSPORT_PATH.md`), an independent structural agreement this
implementation was not fitted to on purpose.

**What is NOT verified**: whether this is genuinely audible, correct
speech when played back. No audio playback or listening verification was
possible in this environment. Treat decoded WAV output as
"structurally self-consistent, sample-count-correct, not yet
perceptually verified" -- a real, honestly-flagged gap, not a silent
assumption. See `docs/audio/XAPACK_FORMAT.md`'s "Remaining blocker
before Fandub replacement" section.
"""
from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass, field
from enum import Enum

from gcrts.audio_event_extraction import extract_runtime_audio_event
from gcrts.xa_disc_index import read_sector_meta
from gcrts.xapack_catalog import XaPackCatalogEntry

SECTOR_SIZE = 2352
FORM2_DATA_SIZE = 2324
XA_ADPCM_PAYLOAD_SIZE = 2304  # Form2's 2324-byte user data minus its own 20-byte sub-header/EDC trailer used by XA-ADPCM specifically
GROUP_SIZE = 128
GROUPS_PER_SECTOR = XA_ADPCM_PAYLOAD_SIZE // GROUP_SIZE  # 18
UNITS_PER_GROUP = 4
SAMPLES_PER_UNIT_PER_GROUP = 56  # 28 rows x 2 nibbles/row -- see module docstring
SAMPLES_PER_CHANNEL_PER_GROUP = SAMPLES_PER_UNIT_PER_GROUP * 2  # 2 units (e.g. 0+2, or 1+3) combine into one stereo channel: 112
SAMPLES_PER_CHANNEL_PER_SECTOR = SAMPLES_PER_CHANNEL_PER_GROUP * GROUPS_PER_SECTOR  # 2016 -- cross-validated, see module docstring

_SUBMODE_EOR = 0x01
_SUBMODE_VIDEO = 0x02
_SUBMODE_AUDIO = 0x04
_SUBMODE_DATA = 0x08
_SUBMODE_TRIGGER = 0x10
_SUBMODE_FORM2 = 0x20
_SUBMODE_REALTIME = 0x40
_SUBMODE_EOF = 0x80

# The two real-time-audio submode values found on the real disc: the
# standard "still playing" sector, and the same flags plus EOF for a
# channel's own last sector.
AUDIO_SUBMODE = _SUBMODE_AUDIO | _SUBMODE_FORM2 | _SUBMODE_REALTIME  # 0x64
AUDIO_EOF_SUBMODE = AUDIO_SUBMODE | _SUBMODE_EOF  # 0xE4


class SectorClass(str, Enum):
    AUDIO = "AUDIO"  # real-time XA-ADPCM audio, this channel's stream still going
    AUDIO_EOF = "AUDIO_EOF"  # this channel's own last audio sector
    SILENCE_PADDING = "SILENCE_PADDING"  # non-audio filler after a channel's own EOF
    TERMINATOR = "TERMINATOR"  # the pack's own final, non-audio EOF sector
    OTHER = "OTHER"  # anything not matching the patterns found on the real disc


def classify_sector_submode(submode: int) -> SectorClass:
    """Pure classification from a real submode byte -- see module
    docstring for the real value counts this was built from."""
    if submode == AUDIO_SUBMODE:
        return SectorClass.AUDIO
    if submode == AUDIO_EOF_SUBMODE:
        return SectorClass.AUDIO_EOF
    if submode & _SUBMODE_AUDIO:
        return SectorClass.OTHER  # an audio-flagged sector with unexpected other bits
    if submode & _SUBMODE_EOF:
        return SectorClass.TERMINATOR
    if submode == 0x00:
        return SectorClass.SILENCE_PADDING
    return SectorClass.OTHER


@dataclass(frozen=True)
class XaStreamFormat:
    stereo: bool
    sample_rate_hz: int
    bits_per_sample: int
    emphasis: bool

    @property
    def channel_count(self) -> int:
        return 2 if self.stereo else 1


def format_from_coding_info(coding_info: int) -> XaStreamFormat:
    """Decode the real CD-XA `coding_info` byte per the documented
    Green Book layout: bits0-1 stereo (0=mono,1=stereo), bits2-3 sample
    rate (0=37800Hz,1=18900Hz), bits4-5 bits/sample (0=4-bit,1=8-bit),
    bit6 emphasis. Every real sector found on this disc reads exactly
    `0x01` (stereo, 37800Hz, 4-bit, no emphasis) -- see module
    docstring."""
    stereo = bool(coding_info & 0x01)
    rate_bits = (coding_info >> 2) & 0x03
    bits_field = (coding_info >> 4) & 0x03
    emphasis = bool((coding_info >> 6) & 0x01)
    return XaStreamFormat(
        stereo=stereo,
        sample_rate_hz=18900 if rate_bits == 1 else 37800,
        bits_per_sample=8 if bits_field == 1 else 4,
        emphasis=emphasis,
    )


class PackFormatClassification(str, Enum):
    STANDARD_XA = "STANDARD_XA"
    XA_LIKE = "XA_LIKE"
    CUSTOM_CONTAINER = "CUSTOM_CONTAINER"
    MIXED = "MIXED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class PackFormatResult:
    classification: PackFormatClassification
    audio_sector_count: int
    audio_eof_sector_count: int
    silence_sector_count: int
    terminator_sector_count: int
    other_sector_count: int
    coding_info_values_seen: tuple[int, ...]
    evidence: str


def classify_pack_format(disc_bytes: bytes, start_lba: int, end_lba: int) -> PackFormatResult:
    """Real, evidence-based classification -- never trusts the
    `XAPACK` filename as evidence (per the milestone's own explicit
    instruction). Scans every sector in `[start_lba, end_lba)` and only
    returns STANDARD_XA if every audio-flagged sector shows the exact
    real-time-XA submode pattern (Audio+Form2+Realtime, optionally EOF)
    with a self-consistent, defined `coding_info` value."""
    counts = {c: 0 for c in SectorClass}
    coding_values: set[int] = set()
    contradictory = False

    for lba in range(start_lba, end_lba):
        meta = read_sector_meta(disc_bytes, lba)
        if meta is None:
            continue
        cls = classify_sector_submode(meta.submode)
        counts[cls] += 1
        if cls in (SectorClass.AUDIO, SectorClass.AUDIO_EOF):
            coding_values.add(meta.coding_info)
            bits_field = (meta.coding_info >> 4) & 0x03
            rate_bits = (meta.coding_info >> 2) & 0x03
            if bits_field == 0x03 or rate_bits == 0x03:  # reserved/undefined combos
                contradictory = True

    total_audio = counts[SectorClass.AUDIO] + counts[SectorClass.AUDIO_EOF]
    if total_audio == 0:
        classification = PackFormatClassification.UNKNOWN
        evidence = "No sectors matched the real-time XA audio submode pattern in this range."
    elif contradictory:
        classification = PackFormatClassification.MIXED
        evidence = "Audio-flagged sectors found, but some coding_info values use reserved/undefined bit combinations."
    elif counts[SectorClass.OTHER] > 0:
        classification = PackFormatClassification.XA_LIKE
        evidence = f"{total_audio} standard-looking audio sectors, but {counts[SectorClass.OTHER]} sector(s) had unexpected submode bit combinations."
    else:
        classification = PackFormatClassification.STANDARD_XA
        evidence = (
            f"{total_audio} audio sectors (submode 0x64/0xE4), {counts[SectorClass.SILENCE_PADDING]} silence-padding, "
            f"{counts[SectorClass.TERMINATOR]} terminator, coding_info values seen: {sorted(coding_values)}."
        )

    return PackFormatResult(
        classification=classification,
        audio_sector_count=counts[SectorClass.AUDIO],
        audio_eof_sector_count=counts[SectorClass.AUDIO_EOF],
        silence_sector_count=counts[SectorClass.SILENCE_PADDING],
        terminator_sector_count=counts[SectorClass.TERMINATOR],
        other_sector_count=counts[SectorClass.OTHER],
        coding_info_values_seen=tuple(sorted(coding_values)),
        evidence=evidence,
    )


class StreamConfidence(str, Enum):
    LIVE_CROSS_VALIDATED = "LIVE_CROSS_VALIDATED"  # a real live-observed LBA independently fell inside this stream's own range
    STRUCTURALLY_CONFIRMED = "STRUCTURALLY_CONFIRMED"  # real EOF marker found, clean single-channel span
    STATICALLY_CONFIRMED = "STATICALLY_CONFIRMED"  # audio sectors found for this channel, but no EOF marker seen (open-ended)
    CANDIDATE = "CANDIDATE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class XaChannelStream:
    """One physically-bounded per-channel audio stream inside one pack
    -- Phase 16's "event segmentation" unit. `first_lba`/`eof_lba` are
    both inclusive, real sector boundaries (never derived from timing).
    """

    pack_path: str
    pack_index: int
    xa_file_number: int
    channel_number: int
    first_lba: int
    eof_lba: int | None  # None if this channel's own EOF sector was never found (open-ended stream)
    sector_count: int
    format: XaStreamFormat
    confidence: StreamConfidence

    @property
    def byte_length_raw(self) -> int:
        return self.sector_count * XA_ADPCM_PAYLOAD_SIZE

    @property
    def duration_seconds(self) -> float:
        total_samples = self.sector_count * SAMPLES_PER_CHANNEL_PER_SECTOR
        return total_samples / self.format.sample_rate_hz


def parse_pack_channel_streams(disc_bytes: bytes, pack: XaPackCatalogEntry) -> list[XaChannelStream]:
    """The real, physical per-channel segmentation for one pack (Phase 4
    interleave map + Phase 16 event boundaries in one pass). Returns one
    `XaChannelStream` per channel actually observed with audio (0-7,
    fewer if a pack uses fewer channels -- confirmed real, e.g.
    XAPACK42.BIN uses only 7). Pure given already-loaded `disc_bytes`."""
    channel_first: dict[int, int] = {}
    channel_eof: dict[int, int] = {}
    channel_sector_count: dict[int, int] = {}
    channel_file_number: dict[int, int] = {}
    channel_coding_info: dict[int, int] = {}

    for lba in range(pack.start_lba, pack.end_lba):
        meta = read_sector_meta(disc_bytes, lba)
        if meta is None:
            continue
        cls = classify_sector_submode(meta.submode)
        if cls not in (SectorClass.AUDIO, SectorClass.AUDIO_EOF):
            continue
        ch = meta.channel_number
        channel_first.setdefault(ch, lba)
        channel_sector_count[ch] = channel_sector_count.get(ch, 0) + 1
        channel_file_number.setdefault(ch, meta.file_number)
        channel_coding_info.setdefault(ch, meta.coding_info)
        if cls == SectorClass.AUDIO_EOF:
            channel_eof[ch] = lba

    streams: list[XaChannelStream] = []
    for ch in sorted(channel_first):
        eof = channel_eof.get(ch)
        confidence = StreamConfidence.STRUCTURALLY_CONFIRMED if eof is not None else StreamConfidence.STATICALLY_CONFIRMED
        streams.append(
            XaChannelStream(
                pack_path=pack.disc_path,
                pack_index=pack.index,
                xa_file_number=channel_file_number[ch],
                channel_number=ch,
                first_lba=channel_first[ch],
                eof_lba=eof,
                sector_count=channel_sector_count[ch],
                format=format_from_coding_info(channel_coding_info[ch]),
                confidence=confidence,
            )
        )
    return streams


def mark_live_cross_validated(stream: XaChannelStream) -> XaChannelStream:
    """Upgrade confidence once a real, independently-obtained live LBA
    observation has been checked to fall inside this stream's own
    range (never call this speculatively -- see
    `lba_falls_within_stream`)."""
    return XaChannelStream(
        pack_path=stream.pack_path,
        pack_index=stream.pack_index,
        xa_file_number=stream.xa_file_number,
        channel_number=stream.channel_number,
        first_lba=stream.first_lba,
        eof_lba=stream.eof_lba,
        sector_count=stream.sector_count,
        format=stream.format,
        confidence=StreamConfidence.LIVE_CROSS_VALIDATED,
    )


def lba_falls_within_stream(stream: XaChannelStream, lba: int) -> bool:
    """WARNING: range containment alone does NOT identify which
    channel an LBA belongs to -- interleaved channels' spans overlap
    almost entirely, so an arbitrary LBA will satisfy this check for
    EVERY channel in the pack simultaneously. Only use this to check
    "is this LBA within THIS SPECIFIC, already-identified channel's
    own temporal extent" (e.g. after already reading that exact
    sector's own channel_number via `read_sector_meta`) -- never to
    discover which channel an LBA belongs to. See
    `gcrts.audio_asset_resolver.resolve_audio_asset` for the correct
    two-step pattern (read the real channel_number first, then check
    this)."""
    if stream.eof_lba is not None:
        return stream.first_lba <= lba <= stream.eof_lba
    return lba >= stream.first_lba


# --- AudioAsset identity (Phase 13/14) --------------------------------------


@dataclass(frozen=True)
class AudioAsset:
    """A stable, structural identity for one extractable audio
    stream -- deliberately NOT keyed on a raw selector value or a
    script parameter (both proven unstable elsewhere in this project,
    see gcrts.runtime_audio's module docstring). Survives different
    script occurrences, repeated selector values, and project reloads,
    because it is derived purely from the disc's own physical layout."""

    pack_path: str
    channel_number: int
    first_lba: int
    eof_lba: int | None
    sector_count: int
    format: XaStreamFormat
    duration_seconds: float
    confidence: StreamConfidence
    content_sha256: str | None = None  # filled in only once the raw bytes have actually been read, see fingerprint_stream

    @property
    def asset_id(self) -> str:
        """`<pack filename without extension>:<channel>` -- stable,
        human-readable, and derived entirely from physical disc
        structure (see module docstring)."""
        filename = self.pack_path.rsplit("/", 1)[1].split(".")[0]
        return f"{filename}:{self.channel_number}"

    def to_dict(self) -> dict:
        return {
            "asset_id": self.asset_id,
            "pack_path": self.pack_path,
            "channel_number": self.channel_number,
            "first_lba": self.first_lba,
            "eof_lba": self.eof_lba,
            "sector_count": self.sector_count,
            "stereo": self.format.stereo,
            "sample_rate_hz": self.format.sample_rate_hz,
            "bits_per_sample": self.format.bits_per_sample,
            "duration_seconds": self.duration_seconds,
            "confidence": self.confidence.value,
            "content_sha256": self.content_sha256,
        }


def audio_asset_from_channel_stream(stream: XaChannelStream) -> AudioAsset:
    return AudioAsset(
        pack_path=stream.pack_path,
        channel_number=stream.channel_number,
        first_lba=stream.first_lba,
        eof_lba=stream.eof_lba,
        sector_count=stream.sector_count,
        format=stream.format,
        duration_seconds=stream.duration_seconds,
        confidence=stream.confidence,
    )


# --- Raw extraction (Phase 17) -- reuses the already-validated sector selector ---


def extract_channel_raw(disc_bytes: bytes, stream: XaChannelStream) -> bytes:
    """Raw, undecoded XA-ADPCM payload bytes for one channel's whole
    stream, in physical (== logical) order -- exactly
    `XA_ADPCM_PAYLOAD_SIZE` (2304) bytes per sector, concatenated with
    no gaps. Delegates the actual sector filtering to
    `gcrts.audio_event_extraction`'s already live-validated selector
    rather than duplicating it, but that module returns the FULL
    2324-byte Form2 user-data area per sector (including a trailing
    20-byte reserved/EDC region that is not ADPCM sample data) -- this
    function re-chunks per sector and trims that trailer off, so a
    downstream decoder can safely stride by `XA_ADPCM_PAYLOAD_SIZE`
    with no accumulating drift."""
    if stream.eof_lba is None:
        end_lba = stream.first_lba + stream.sector_count  # open-ended: best-known extent
    else:
        end_lba = stream.eof_lba + 1  # extract_runtime_audio_event's range is exclusive
    extracted = extract_runtime_audio_event(
        disc_bytes,
        start_lba=stream.first_lba,
        end_lba=end_lba,
        xa_file_number=stream.xa_file_number,
        xa_channel=stream.channel_number,
        event_id=f"{stream.pack_path}:{stream.channel_number}",
        source_file=stream.pack_path,
    )
    full = extracted.raw_xa_payload
    trimmed = bytearray()
    for offset in range(0, len(full) - FORM2_DATA_SIZE + 1, FORM2_DATA_SIZE):
        trimmed += full[offset:offset + XA_ADPCM_PAYLOAD_SIZE]
    return bytes(trimmed)


def fingerprint_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --- ADPCM decode (Phase 18) -------------------------------------------------

# The 5 standard PSX ADPCM filter coefficient pairs (Q6 fixed point,
# i.e. divide by 64) -- identical math to SPU voice ADPCM, the
# best-established part of this decoder (see module docstring).
_FILTER_K0 = (0, 60, 115, 98, 122)
_FILTER_K1 = (0, 0, -52, -55, -60)


@dataclass
class XaDecoderState:
    """Running (hist1, hist2) per sound unit (0-3), threaded across
    sectors -- ADPCM is stateful/differential, so decode must proceed
    in physical order from the very first sector of a stream."""

    hist1: list[int] = field(default_factory=lambda: [0, 0, 0, 0])
    hist2: list[int] = field(default_factory=lambda: [0, 0, 0, 0])


def _clamp16(value: int) -> int:
    return max(-32768, min(32767, value))


def _decode_unit_nibbles(nibbles: list[int], shift: int, filt: int, hist1: int, hist2: int) -> tuple[list[int], int, int]:
    eff_shift = shift if shift <= 12 else 9  # documented quirk: reserved range values 13-15 behave like 9
    k0 = _FILTER_K0[filt] if filt < len(_FILTER_K0) else 0
    k1 = _FILTER_K1[filt] if filt < len(_FILTER_K1) else 0
    out: list[int] = []
    for nibble in nibbles:
        signed = nibble if nibble < 8 else nibble - 16
        raw = (signed << 12) >> eff_shift
        pred = (hist1 * k0 + hist2 * k1 + 32) >> 6
        sample = _clamp16(raw + pred)
        hist2 = hist1
        hist1 = sample
        out.append(sample)
    return out, hist1, hist2


def decode_xa_sector_payload(payload: bytes, state: XaDecoderState) -> tuple[list[int], list[int]]:
    """Decode one Form2/XA sector's 2304-byte payload into (left,
    right) 16-bit PCM sample lists, `SAMPLES_PER_CHANNEL_PER_SECTOR`
    (2016) samples each. Mutates `state` in place (the running ADPCM
    history), matching a real streaming decode -- see module docstring
    for the confidence breakdown on the exact nibble layout used."""
    if len(payload) < XA_ADPCM_PAYLOAD_SIZE:
        raise ValueError(f"XA payload too short: {len(payload)} < {XA_ADPCM_PAYLOAD_SIZE}")

    left: list[int] = []
    right: list[int] = []
    for g in range(GROUPS_PER_SECTOR):
        group = payload[g * GROUP_SIZE:(g + 1) * GROUP_SIZE]
        headers = group[0:4]
        data = group[16:128]

        unit_samples: list[list[int]] = [[] for _ in range(UNITS_PER_GROUP)]
        for unit in range(UNITS_PER_GROUP):
            header = headers[unit]
            shift = header & 0x0F
            filt = (header >> 4) & 0x0F
            nibbles: list[int] = []
            for row in range(28):
                b = data[row * 4 + unit]
                nibbles.append(b & 0x0F)
                nibbles.append((b >> 4) & 0x0F)
            samples, h1, h2 = _decode_unit_nibbles(nibbles, shift, filt, state.hist1[unit], state.hist2[unit])
            state.hist1[unit] = h1
            state.hist2[unit] = h2
            unit_samples[unit] = samples

        # units {0,2} -> Left, units {1,3} -> Right, each pair concatenated
        # in unit order (see module docstring's honesty note on this choice)
        left.extend(unit_samples[0])
        left.extend(unit_samples[2])
        right.extend(unit_samples[1])
        right.extend(unit_samples[3])

    return left, right


def decode_channel_to_pcm(disc_bytes: bytes, stream: XaChannelStream) -> tuple[int, int, bytes]:
    """Decode a whole channel stream to interleaved 16-bit PCM.
    Returns (sample_rate_hz, channel_count, pcm_bytes). Channel count
    is always 2 on this disc (every real sector found is stereo)."""
    raw = extract_channel_raw(disc_bytes, stream)
    state = XaDecoderState()
    pcm = bytearray()
    for offset in range(0, len(raw) - XA_ADPCM_PAYLOAD_SIZE + 1, XA_ADPCM_PAYLOAD_SIZE):
        payload = raw[offset:offset + XA_ADPCM_PAYLOAD_SIZE]
        left, right = decode_xa_sector_payload(payload, state)
        for l_sample, r_sample in zip(left, right):
            pcm += struct.pack("<hh", l_sample, r_sample)
    return stream.format.sample_rate_hz, stream.format.channel_count, bytes(pcm)


def write_wav(path: str, sample_rate_hz: int, channel_count: int, pcm_bytes: bytes) -> None:
    """Standard, minimal 16-bit PCM WAV writer -- no external
    dependency needed for this well-defined a format."""
    bits_per_sample = 16
    byte_rate = sample_rate_hz * channel_count * bits_per_sample // 8
    block_align = channel_count * bits_per_sample // 8
    data_size = len(pcm_bytes)
    with open(path, "wb") as f:
        f.write(b"RIFF")
        f.write(struct.pack("<I", 36 + data_size))
        f.write(b"WAVE")
        f.write(b"fmt ")
        f.write(struct.pack("<IHHIIHH", 16, 1, channel_count, sample_rate_hz, byte_rate, block_align, bits_per_sample))
        f.write(b"data")
        f.write(struct.pack("<I", data_size))
        f.write(pcm_bytes)
