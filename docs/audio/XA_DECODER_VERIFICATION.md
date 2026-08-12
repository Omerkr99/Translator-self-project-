# GCRTS XA-ADPCM Decoder Verification / Golden Audio Validation

Milestone goal: verify `gcrts.xapack.decode_channel_to_pcm()` against a
trusted, independent reference, close the nibble/interleave uncertainty
the prior milestone (`XAPACK_FORMAT.md`) honestly flagged, and freeze a
Golden Audio Asset. New module: `gcrts/xa_decoder_verify.py`. Small
additions to `gcrts/xapack.py` (`AudioAsset.decode_confidence`/
`decode_supported`/`pcm_sample_count`) and `gcrts/audio_asset_resolver.py`
(`decode_audio_asset`, `export_audio_asset_wav`).

## Golden asset

`XAPACK08:7` -- `DAT/XA1/XAPACK08.BIN` channel 7, physical bounds
LBA `126225`-`129273` (382 sectors), duration **20.373 seconds**. Chosen
because it is already the project's strongest cross-validated real
anchor: the confirmed dialogue cue `KNOWN_CUE_SOURCES[127]`
(`xa_channel=7`, observed LBA `126921`) lands exactly inside this
stream's own physical bounds.

## Current decoder before verification

Two "sound units" combined per stereo channel via block concatenation
(unit0+unit2 -> Left, unit1+unit3 -> Right), with 4 header bytes read
from group offset `0-3`. This was the best-effort layout from the prior
milestone's own reading of public CD-XA documentation, explicitly
flagged there as *not independently verified*.

## Reference decoder

**FFmpeg 7.1** (`imageio-ffmpeg` PyPI package, which bundles a real,
independent ffmpeg binary -- no code from this project went into it).
Two genuinely independent FFmpeg components were used:

- **`psxstr` demuxer** ("Sony Playstation STR") -- fed the *exact real
  disc bytes* for `XAPACK08.BIN` (a raw copy, `dd`-style, no
  reformatting) via `-f psxstr`. It auto-detected **exactly 8 streams,
  all `adpcm_xa, 37800 Hz, stereo`** -- independently confirming this
  project's own structural findings (8-way interleave, stereo,
  37800 Hz) before any PCM comparison even started.
- **`adpcm_xa` decoder** (`libavcodec/adpcm.c`'s `xa_decode`) -- a
  mature, community-maintained implementation of PS1 CD-XA ADPCM,
  used via `ffmpeg -f psxstr -i <raw pack bytes> -map 0:<channel> -c:a
  pcm_s16le -f wav <out>.wav`.

Command used for the golden asset:
```
ffmpeg -y -f psxstr -i xapack08_raw.bin -map 0:7 -c:a pcm_s16le -f wav ffmpeg_ch7.wav
```
Output: `adpcm_xa, 37800 Hz, stereo, s16p` decoded to 16-bit PCM WAV,
`time=00:00:20.37` -- matching this project's own computed duration
exactly before any sample-level comparison was even run.

## Sample-count comparison

**Exact match from the start**, every asset tested: internal and
reference both produced `1540224` total samples (`770112`
frames/channel) for the golden asset -- confirming the `SAMPLES_PER_
CHANNEL_PER_SECTOR = 2016` structural math was already right. Sample
*count* was never the problem; sample *content* was.

## PCM comparison

**First attempt: 1.4417% exact match** (22,205 / 1,540,224 samples) --
a real, decisive failure, not "close enough." The first sample matched
exactly (`-6 == -6`, expected regardless of layout choice, since it's
determined purely by the very first nibble consumed) and diverged
immediately after.

Rather than keep guessing at candidate orderings blindly, FFmpeg's own
open-source `xa_decode` (`libavcodec/adpcm.c`, fetched and read
directly -- not via a paraphrased summary, which on a first pass
produced index expressions ambiguous enough not to trust blindly) was
used as ground truth.

**After the correction below: 100.0000% exact match, zero mismatches**,
verified on the golden asset and 4 additional real assets (see
"Multi-asset verification").

## Decoder bugs found

1. **Wrong header byte positions.** Headers are actually read from
   group offset **`4-11`** (8 bytes: 4 `(low-nibble-header,
   high-nibble-header)` pairs, one pair per iteration) -- not offset
   `0-3` as originally assumed. Offsets `0-3` and `12-15` hold
   redundant copies real hardware doesn't need to read.
2. **Wrong nibble-to-channel assignment.** A data byte's low nibble
   feeds the **Left** channel and its high nibble feeds the **Right**
   channel, at the *same* output time position -- not two sequential
   samples of one independent "sound unit" later paired 2-per-channel,
   as originally assumed. Each iteration's low-nibble pass and
   high-nibble pass are each fully sequential (28 samples) with
   independent history chains, not interleaved nibble-by-nibble.
3. **Mono wasn't handled at all**, only discovered once a real mono
   asset was included in multi-asset testing (see below). Mono has no
   L/R split: both nibble-halves of every iteration continue the SAME
   history chain into one output stream.

## Corrections

`gcrts.xapack.decode_xa_sector_payload` was rewritten: headers read
from `group[4+i*2]`/`group[5+i*2]`; each iteration decoded as two
separate sequential 28-sample passes (`_decode_half_block`) over the
same `data[i + row*4]` bytes (low nibble, then high nibble), stereo
using independent Left/Right history chains, mono continuing one chain
across both passes. `decode_channel_to_pcm` and `AudioAsset` updated to
route on `stream.format.stereo` and expose the new `decode_supported`/
`decode_confidence`/`pcm_sample_count` fields.

## Multi-asset verification

| Asset | Pack | Format | Samples | Mismatches |
|---|---|---|---|---|
| `XAPACK08:7` (golden) | `XAPACK08.BIN` | stereo | 1,540,224 | **0** |
| `XAPACK08:0` | `XAPACK08.BIN` (different channel) | stereo | 1,689,408 | **0** |
| `XAPACK00:0` | `XAPACK00.BIN` (largest real pack) | stereo | 25,329,024 | **0** |
| `XAPACK35:3` | `XAPACK35.BIN` (different, small pack) | stereo | 137,088 | **0** |
| `XAPACK42:6` | `XAPACK42.BIN` (real mono exception) | **mono** | 8,064 | **0** |

Five real assets, three different packs, a wide size range, and both
stereo and mono format variants -- **100.0000% exact match on every
one**, zero mismatches. See `gcrts.xa_decoder_verify.GOLDEN_ASSET_
VERIFICATIONS` for the same data as executable evidence.

## Perceptual verification

**Unavailable** -- no audio playback capability exists in this
environment. This is an honest, stated gap: reference-decoder agreement
(above) is standard, accepted practice for validating a decoder
implementation, but it is not the same claim as a human confirming the
audio sounds correct. The exported golden WAV
(`gcrts.audio_asset_resolver.export_audio_asset_wav`) is ready for a
human listener to confirm at any time; doing so would upgrade
`DecoderConfidence.REFERENCE_VERIFIED` to `REFERENCE_AND_PERCEPTUALLY_
VERIFIED`.

## Final decoder status

```
CORRECTED_AND_VERIFIED
```

Real bugs were found and fixed (not zero-bug "VERIFIED"), and the
corrected decoder now matches an independent reference exactly on
every real asset tested (not `MISMATCH_UNRESOLVED`).

## Audio Inspector readiness

**Yes, trustworthy.** `decode_audio_asset`/`export_audio_asset_wav`
(`gcrts.audio_asset_resolver`) give a clean, read-only `AudioAsset ->
(sample_rate, channels, pcm) / .wav file` path, backed by a decoder now
verified against an independent reference rather than merely
structurally self-consistent.

## Fandub readiness

An `AudioAsset` can now be treated as a **known-correct** original: its
decoded audio, duration, sample rate, and channel count are trustworthy
inputs for future caption/translation/replacement-duration-comparison
work -- not just structurally plausible ones.

## Tests

Previous: 666 (roll-forward from `XAPACK_FORMAT.md`'s own count,
already 3 higher than the 619 baseline this milestone's own prompt
cited -- see `CURRENT_SYSTEM_STATUS.md` for the up-to-date figure)
New: 20 (`test_xa_decoder_verify.py`: 14; `test_audio_asset_resolver.py`:
+3; `test_xapack.py`: net +3 replacing 2 stale decode tests with 5
corrected/new ones)
Total: **686 passed**, 0 regressions.

## Remaining blocker before Audio Inspector

None structural -- the decoder is reference-verified and the playback/export backend is real and tested; only UI work remains.

## Remaining blocker before Fandub replacement

Perceptual (by-ear) confirmation of the golden asset is still open, since no audio playback is available in this environment.

## Next milestone

Get a human listener to confirm the exported golden WAV
(`XAPACK08:7`) sounds like correct, intelligible dialogue -- the one
remaining step to `REFERENCE_AND_PERCEPTUALLY_VERIFIED`, after which
the decoder needs no further validation work before Audio Inspector or
Fandub tooling can build on it directly.
