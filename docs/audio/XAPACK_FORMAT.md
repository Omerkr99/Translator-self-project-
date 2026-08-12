# GCRTS XAPACK Raw Format + Audio Asset Discovery

Milestone goal: reverse-engineer the physical audio format inside
`XAPACK*.BIN` files and build direct per-audio-event access, as the
technical foundation for a future workflow: `ScriptUnit -> Audio
Association -> Audio Asset -> Play/Export -> Transcript/Caption ->
Fandub Recording -> Replacement -> Rebuild`. Worked entirely
offline/static this pass, per its own explicit instruction: no SPU
live-capture investigation, byte-level analysis of the real disc image
plus cross-validation against already-established real live anchors.
New modules: `gcrts/xapack_catalog.py`, `gcrts/xapack.py`,
`gcrts/audio_asset_resolver.py`. Small additions to
`gcrts/xa_disc_index.py` (`all_xapack_files()`) and
`gcrts/spu_audio_path.py` (`classify_stream_format()` now returns
`XA_ADPCM`, see below).

## XAPACK physical structure

A byte-level scan of real sectors (`gcrts.xa_disc_index.read_sector_meta`,
already live-validated in prior sessions) across **all 43 real XAPACK
files** (not a sample) found a single, near-universal structure:

- Every audio-carrying sector's `submode` is exactly `0x64` -- Audio
  (bit2) + Form2 (bit5) + Realtime (bit6), nothing else. The textbook
  Green Book / White Book CD-XA "real-time audio sector" signature.
- Every pack interleaves exactly 8 channels (0-7) in strict round-robin
  from its very first sector, zero gaps in the audio region -- a real
  physical 8-way CD-XA interleave, not a "positional artifact" of one
  arbitrarily observed LBA (the caveat `gcrts.xa_disc_index`'s own
  docstring originally raised, before this milestone).
- Each of the 8 channels carries its own independent audio stream,
  terminated by a real, physical **EOF marker**: exactly one sector per
  channel has `submode = 0xE4` (same bits + EOF) at exactly that
  channel's own last audio-flagged sector -- confirmed byte-for-byte:
  the EOF sector's LBA always equals that channel's own highest
  audio-flagged LBA, across every pack checked. After a channel's own
  EOF, its future interleave slots carry silence/padding sectors
  (`submode=0x00`) for the rest of the pack, while other channels
  continue independently.
- Every pack ends with exactly one true file terminator sector
  (`submode=0x80`, or the rarer `0x89` variant seen once, both
  EOF-flagged but not audio-flagged) as its own physically last sector.

Validated across all 43 packs: **41/43 match this model exactly** (8
channels, 1 terminator, each channel's EOF matching its own last audio
sector). The 2 exceptions are minor, explainable, non-contradicting
variations, not counter-evidence:

- `XAPACK42.BIN` (the last, smallest pack) uses only 7 of the 8 channel
  slots -- a legitimate "fewer clips in this pack" variation.
- `XAPACK29.BIN` has one extra terminator-family sector (`submode=0x89`
  -- EOR+Data+EOF, still landing on the pack's own physically final
  sector) alongside a standard `0x80` one -- just a terminator-flag
  variant, not a hidden index/table (its raw bytes were inspected;
  nothing beyond an ordinary trailing terminator sector was found
  there).

Format classification: `gcrts.xapack.classify_pack_format()` returns
`STANDARD_XA`, `XA_LIKE`, `CUSTOM_CONTAINER`, `MIXED`, or `UNKNOWN`
purely from the real physical evidence above -- never from the
filename. Every pack tested classifies `STANDARD_XA`.

## Stream format

**`XA_ADPCM`** -- confirmed, not inferred. Every real audio sector's
`coding_info` byte is exactly `0x01`: stereo (bits0-1=1), 37800 Hz
(bits2-3=0), 4-bit ADPCM (bits4-5=0), no emphasis
(`gcrts.xapack.format_from_coding_info`). One legitimate exception was
found: a very short (2-sector, ~0.1s) clip on `XAPACK42.BIN` channel 6
uses mono encoding -- a real, valid format variation, not corruption
(`classify_pack_format` correctly does not flag mono/stereo as
contradictory, since both are defined, valid XA-ADPCM configurations).

This independently explains an earlier milestone's finding
(`AUDIO_TRANSPORT_PATH.md`): the SPU Debug window's static `XA` panel
reading of `Frequency: 37800`/`Stereo: 1`/`Samples: 2016` was never
meaningless -- it is an accurate, constant report of the real hardware
decode configuration. It doesn't toggle per dialogue event because the
*format* never changes, only the *content* does. `Samples: 2016` is
independently cross-validated by this milestone's own decode math: 18
sound groups/sector x (2 sound units x 56 samples/unit) = 2016 decoded
samples per channel per sector, matching exactly
(`gcrts.xapack.SAMPLES_PER_CHANNEL_PER_SECTOR`).

`gcrts.spu_audio_path.classify_stream_format()` now returns
`StreamFormat.XA_ADPCM` (previously `UNKNOWN` across many prior
milestones) -- see that module's own updated docstring for the full
chain from this evidence back to the transport question.

## Internal index/table

None found. Phase 5's search (headers/offset tables/cue tables inside a
pack, multiple endian interpretations) came back genuinely empty: the
only non-audio content within a pack is the per-channel silence padding
after that channel's own EOF, and the pack-final terminator sector. No
in-band offset/length table was located. This is reported honestly as
a real negative, not a gap -- the per-channel EOF marker (see "Event
segmentation" below) turned out to be sufficient for segmentation
without needing a separate index structure.

## Event segmentation

Solved structurally, not by timing. Each channel's own audio stream is
bounded by `[first_lba, eof_lba]` (both inclusive), where `eof_lba` is
that channel's own real, physical EOF-flagged sector
(`gcrts.xapack.XaChannelStream`, built by
`parse_pack_channel_streams()`). This gives up to 8 independently
extractable audio streams per pack, each with exact physical sector
boundaries -- never derived from an arbitrary wall-clock duration.

**Important, real bug caught and fixed during this milestone**: because
channels are physically interleaved, their `[first_lba, eof_lba]` spans
overlap almost entirely -- a single LBA satisfies "is this LBA within
channel N's overall span" for *every* channel in the pack
simultaneously. An early version of the runtime resolver
(`gcrts.audio_asset_resolver.resolve_audio_asset`) used range
containment alone to pick a channel and returned the wrong one (channel
0 instead of the ground-truth channel 7) for a known anchor. Fixed by
reading the exact sector's own `channel_number` subheader byte first,
then using range containment only as a secondary bounds check. See
`gcrts.xapack.lba_falls_within_stream`'s own docstring warning, and
`tests/test_audio_asset_resolver.py`'s
`test_resolve_audio_asset_does_not_confuse_overlapping_channel_spans`
regression test.

## Known ScriptUnit mapping

Cross-validated against two real, independently-established live LBA
anchors already on record elsewhere in this project (not re-captured
this pass, per the milestone's own "don't re-run live capture"
instruction):

- The confirmed dialogue cue (`gcrts.runtime_audio.KNOWN_CUE_SOURCES[127]`:
  `xa_channel=7`, observed LBA `126921`, source `XAPACK08.BIN`) --
  `resolve_audio_asset(disc_bytes, 126921)` returns channel **7**'s own
  physically-bounded stream (LBA `126225`-`129273`), exactly matching
  the ground truth. Neither the model nor the anchor were adjusted to
  force this match -- the model was built purely from physical sector
  evidence, and only checked against the anchor afterward.
- A second, independent live capture landed exactly on `XAPACK06.BIN`'s
  own start LBA (`116010`) -- resolves to channel 0's own first sector,
  exactly as the model predicts for a position that IS a channel's
  literal first sector.

## AudioAsset model

`gcrts.xapack.AudioAsset` -- a stable identity deliberately NOT keyed on
a raw selector or script parameter (both already proven unstable
elsewhere in this project, see `gcrts.runtime_audio`'s own module
docstring). `asset_id` is `<pack filename>:<channel>` (e.g.
`"XAPACK08:7"`), derived purely from physical disc structure, so it
survives different script occurrences, repeated selector values, and
project reloads. Carries: pack path, channel number, physical LBA
range, sector count, format (stereo/rate/bits), computed duration, and
an explicit confidence label
(`StreamConfidence`: `LIVE_CROSS_VALIDATED` > `STRUCTURALLY_CONFIRMED`
> `STATICALLY_CONFIRMED` > `CANDIDATE` > `UNKNOWN`).

## Extraction

**Both raw and decoded WAV**, implemented and tested against real disc
bytes.

- **Raw**: `gcrts.xapack.extract_channel_raw` reuses the
  already-validated `gcrts.audio_event_extraction.extract_runtime_audio_event`
  sector selector (never duplicates the filtering logic), then trims
  each sector's own trailing 20-byte reserved/EDC region so the result
  is a clean, gap-free concatenation of exactly the ADPCM payload
  bytes. A real alignment bug was caught and fixed here too: the first
  version didn't trim the trailer, causing the decoder's fixed-size
  stride to drift out of alignment with real sector boundaries after
  the first sector.
- **Decoded WAV**: `gcrts.xapack.decode_channel_to_pcm` +
  `write_wav`. See "Playability" below for the honest confidence
  breakdown on the decoder itself.

## Playability

**Yes, structurally** -- a full channel (real channel 7 of
`XAPACK08.BIN`, the known dialogue cue's own confirmed stream) was
decoded end-to-end to a playable 16-bit stereo WAV file. Two honest
caveats:

1. **The core ADPCM math is high-confidence**: the standard 5-filter-pair
   PSX ADPCM sample formula (identical to SPU voice ADPCM), implemented
   and cross-validated by an exact sample-count match (2016
   samples/channel/sector, independently derived from both the decode
   math and the SPU Debug window's own earlier static reading).
2. **The exact sound-group nibble/byte interleave layout is NOT
   independently verified** against a reference decoder or by
   listening (no audio playback was possible in this environment). The
   implementation uses the most commonly cited public CD-XA layout and
   passed every structural self-test run against it: correct output
   sample count, no clipping/saturation after fixing the alignment bug
   above (min/max moved from a saturated ±32768 to a believable
   ±16000-19000 range), non-degenerate variance, and a real,
   speech-plausible energy envelope (a 20-second decode of the known
   dialogue channel showed a natural rise-sustain-decay shape, ending
   in near-silence exactly at the stream's own EOF marker -- see
   `gcrts.xapack`'s module docstring for the full self-test numbers).
   This is real, honest corroborating evidence, not proof of
   perceptual correctness.

## Duration

Yes, reliably, from real structural data:
`sector_count * SAMPLES_PER_CHANNEL_PER_SECTOR / sample_rate_hz`
(`XaChannelStream.duration_seconds`/`AudioAsset.duration_seconds`).
Not derived from any wall-clock/timing observation. The known dialogue
cue's channel-7 stream (382 sectors) computes to **20.37 seconds**.
Independent runtime-duration cross-validation (Phase 19 -- comparing
this to an actually-observed audible duration) was not performed this
pass (would require a live capture, explicitly out of scope this
milestone).

## Fandub readiness

An `AudioAsset` can now be represented with: a real, playable/exportable
original (raw + decoded WAV), a known duration, a real script
association bridge (see "Runtime bridge" below), and a stable identity
ready to carry caption/translation/replacement metadata via the
existing `gcrts.audio_caption` layer (already deliberately scoped to
compose with an `AudioAsset`, per its own module docstring). Actual
replacement/injection/time-stretching, and the caption/translation
attachment itself, are explicitly out of scope this pass (per the
milestone's own instruction) -- only the data-model readiness was
built.

## Runtime bridge

**Yes.** `gcrts.audio_asset_resolver.resolve_from_script_audio_association`
takes an existing `ScriptAudioAssociation` (`gcrts.script_audio_association`,
already live-validated in an earlier milestone) and its embedded
`RuntimeAudioEvent`'s real `start_lba`, and resolves it straight to an
`AudioAsset` via `resolve_audio_asset` -- never falling back to the raw
selector/parameter value, both already proven unstable. This closes the
loop the milestone's own desired workflow needed:
`ScriptUnit -> ScriptAudioAssociation -> resolve_from_script_audio_association -> AudioAsset`.

## Tests

**666 passed** (619 baseline + 47 new: `test_xapack_catalog.py` (8),
`test_xapack.py` (28), `test_audio_asset_resolver.py` (11), 2 new in
`test_xa_disc_index.py`, plus `test_spu_audio_path.py`'s
`classify_stream_format` tests updated from UNKNOWN to XA_ADPCM). No
regressions.

## Remaining blocker before Audio Inspector

None structural -- the data model, extraction, and resolver are all
real and tested; a UI would need only to call `resolve_audio_asset`
and `decode_channel_to_pcm`/`write_wav`, which this milestone
deliberately did not build (out of scope: "do not build the full
polished UI yet").

## Remaining blocker before Fandub replacement

The decoded audio's exact nibble-interleave layout has not been
perceptually (by-ear) verified, so decoded WAV output should be treated
as "structurally sound, not yet confirmed correct-sounding" until a
listening or reference-decoder cross-check is done.

## Next milestone

Get a real listening/reference-decoder verification of
`decode_channel_to_pcm`'s output (e.g. play the extracted
`XAPACK08.BIN` channel 7 WAV against the same, already-confirmed
audible dialogue line, or diff against an established open-source XA
decoder like the one in `vgmstream`/`ffmpeg` if available) -- this is
the one gap between "structurally proven" and "known correct" left by
this pass, and resolving it would upgrade every decoded asset's
confidence at once rather than requiring a re-check per asset.
