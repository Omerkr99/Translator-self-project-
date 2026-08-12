# Audio Asset Model

A reference for the data model this project now uses to represent one
extractable audio stream, and how to get from a script occurrence to
one. For the reverse-engineering story behind *why* this model looks
the way it does, see `XAPACK_FORMAT.md` -- this doc is the "how to use
it" companion.

## Why a new identity, not the existing selector/parameter

Two things already proven unstable elsewhere in this project were
deliberately NOT used as an asset's identity:

- The raw script parameter (`ScriptAudioAssociation.raw_parameter`) --
  the same value (127) was live-observed resolving to two different
  physical files at different times (`gcrts.runtime_audio`'s own module
  docstring, Audio Cue Resolution Generalization milestone).
- A live-observed LBA on its own -- correct for identifying content at
  a moment in time, but not a durable identity across sessions.

`AudioAsset.asset_id` (`gcrts/xapack.py`) is instead
`<pack filename>:<channel>` (e.g. `"XAPACK08:7"`), derived purely from
the disc's own physical structure (which channel, in which pack, does
this audio physically live in) -- stable across script occurrences,
selector reuse, and project reloads.

## The pipeline

```
disc bytes
  -> gcrts.xapack_catalog.build_catalog()          # 43 real XAPACK files, real LBA ranges
  -> gcrts.xapack.parse_pack_channel_streams()      # up to 8 real, EOF-bounded channel streams per pack
  -> gcrts.xapack.audio_asset_from_channel_stream() # -> AudioAsset (stable identity + metadata)
  -> gcrts.xapack.extract_channel_raw()             # -> raw ADPCM bytes
  -> gcrts.xapack.decode_channel_to_pcm()           # -> (sample_rate, channels, pcm_bytes)
  -> gcrts.xapack.write_wav()                       # -> a playable .wav file
```

## The runtime bridge

```
ScriptUnit (gcrts.script_unit)
  -> ScriptAudioAssociation (gcrts.script_audio_association, already live-validated)
  -> gcrts.audio_asset_resolver.resolve_from_script_audio_association()
  -> AudioAssetResolution { asset: AudioAsset | None, confidence, evidence }
```

`resolve_from_script_audio_association` pulls the association's
embedded `RuntimeAudioEvent.start_lba` (a real, live-observed disc
position) and hands it to `resolve_audio_asset`, which:

1. Looks up which of the 43 real packs the LBA falls in
   (`gcrts.xapack_catalog.catalog_entry_for_lba`).
2. Reads that **exact** sector's own `channel_number` subheader byte
   (`gcrts.xa_disc_index.read_sector_meta`) -- **never** infers the
   channel from range containment (see the warning below).
3. Finds that channel's own parsed `XaChannelStream` and confirms the
   LBA falls within its real `[first_lba, eof_lba]` bounds.
4. Returns an `AudioAsset` with `StreamConfidence.LIVE_CROSS_VALIDATED`.

### A real pitfall: interleaved channels' spans overlap

Because a pack's 8 channels are physically interleaved, their
`[first_lba, eof_lba]` spans cover almost the same physical range --
**any** LBA in that range satisfies "is this LBA within channel N's
overall span" for every channel at once. Matching by range containment
alone (without first reading the real sector's own channel_number) will
silently pick the wrong channel. This is not a hypothetical: an early
version of `resolve_audio_asset` did exactly this and returned channel
0 for a known channel-7 anchor. Always resolve channel identity from
the sector's own subheader byte first;
`gcrts.xapack.lba_falls_within_stream` is only a secondary bounds
check on an already-identified channel, never a channel finder.

## Confidence, at every level

Two confidence enums, deliberately kept separate:

- `gcrts.xapack.StreamConfidence` -- how sure this project is that a
  parsed `XaChannelStream`'s own boundaries are correct: `CANDIDATE` <
  `STATICALLY_CONFIRMED` (audio found, no EOF marker seen -- open-ended)
  < `STRUCTURALLY_CONFIRMED` (a real EOF marker bounds it) <
  `LIVE_CROSS_VALIDATED` (a real, independently-obtained live LBA was
  checked to fall inside it).
- `gcrts.audio_asset_resolver.ResolutionConfidence` -- how a specific
  *lookup* went: `UNRESOLVED` (LBA not in any known pack) <
  `PACK_ONLY` (in a pack, but not inside any parsed channel's own
  bounds -- e.g. a silence/terminator sector) < `LIVE_LBA_MATCHED`.

Every `AudioAsset`/`AudioAssetResolution` carries its own confidence and
a human-readable `evidence` string -- never presented as a bare boolean.

## Fingerprinting and duplicate detection

`gcrts.xapack.fingerprint_bytes` (SHA-256) is a separate, explicit step
-- `AudioAsset.content_sha256` stays `None` until a caller actually
reads and hashes the raw bytes (fingerprinting the whole disc eagerly
was deliberately not done: 343 real assets exist, and most tooling only
needs a handful at a time).
`gcrts.audio_asset_resolver.find_duplicate_assets` groups already-
fingerprinted assets by hash -- useful for detecting reused dialogue
lines/SFX across script occurrences, but never merges assets
automatically (per this project's own standing rule against acting on
unverified matches).

## Persistence

`gcrts.audio_asset_resolver.build_full_disc_asset_index` computes every
real `AudioAsset` on the whole disc (up to 8 per pack x 43 packs = 343
found on the real disc) in well under a second, since it only scans
sector metadata -- it never decodes audio. `save_asset_index`/
`load_asset_index` provide simple JSON persistence for a caller that
wants one, but this project does not commit a generated index file to
the repo: regenerating from the real disc is cheap and always current,
a stale committed copy would not be.

## What this milestone deliberately did not build

Per its own explicit scope: no injection/replacement, no time
stretching, no recording UI, no subtitle rendering, no bulk
`Extract All Audio` workflow, no full Audio Inspector UI. The data
model above is built so those can be added later without re-deriving
the physical format -- see `XAPACK_FORMAT.md`'s "Next milestone"
section for the one recommended next step (perceptual/reference-decoder
verification of the ADPCM decode itself).
