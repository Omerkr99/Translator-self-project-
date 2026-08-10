# Audio Captions — What Is Being Heard

A semantic layer, deliberately kept separate from `AudioAsset` identity
(`gcrts.xa_disc_index`/`gcrts.runtime_audio` — *where* audio comes from)
and `AudioContext` (`gcrts.audio_context` — *why* that source was
selected). A caption answers a third, different question: what a human
would perceive listening to it. New module: `gcrts/audio_caption.py`.

## What this project can honestly produce on its own

**Exactly one caption source**: `CaptionSource.SCRIPT_CONTEXT` for
`AudioCategory.VOICE_DIALOGUE`, using the real, already-decoded dialogue
text (`ScriptAudioAssociation.dialogue_text`) as the caption. This is
genuine evidence — the literal text the game displays on screen while
that audio plays, extracted by `gcrts.script_decoder` — not an
inference or a guess.

`caption_for_association()` only produces this for a
`SCRIPT_CONTEXT_RESOLVED` association whose control code is confirmed
`sound_or_voice_cue` (the one control code this project has confirmed,
via Stage C's own sector-level decode showing mono 4-bit XA-ADPCM — the
lower-bandwidth profile PS1 games typically reserve for spoken lines —
is used for it) and whose owning unit has real, non-empty text. Live-
verified: a captured real event's caption exactly matches its own
`ScriptAudioAssociation.dialogue_text`, in Japanese, correctly decoded.

## What this project explicitly does NOT do

**No non-dialogue caption text is ever attached to a real event by this
codebase.** The milestone brief's own examples
(`[children laughing in the distance]`, `[door creaks]`,
`[footsteps approaching]`) are illustrations of the FORMAT a caption
could take, not descriptions this project has verified for any actual
captured sound. This environment has no audio playback/listening
capability and no audio classification model integrated — inventing
plausible-sounding SFX/ambient descriptions for real events would be
fabrication, which this project's own standing rules explicitly forbid.

`caption_for_association()` returns `caption_text=None`,
`caption_source=CaptionSource.UNKNOWN`,
`confidence=CaptionConfidence.UNKNOWN` for:

- any association that isn't `SCRIPT_CONTEXT_RESOLVED`,
- any control code other than `sound_or_voice_cue` (this project has no
  evidence-based classification for `AudioCategory.SOUND_EFFECT`/
  `AMBIENT_SOUND`/`MUSIC` at all yet),
- an owning unit whose decoded text is empty/whitespace-only.

## Caption sources modeled but not self-invoked

- `CaptionSource.MANUAL_LISTENING` — for a human operator who has
  actually heard the audio. `create_manual_caption()` exists for this;
  nothing in this codebase calls it with invented text.
- `CaptionSource.USER_DEFINED` — a user-entered/confirmed caption via
  the UI (e.g. a corrected translation of a `SCRIPT_CONTEXT` caption).
  `create_user_caption()` exists for this.
- `CaptionSource.MODEL_INFERRED` — reserved for a future real audio
  classifier integration. Explicitly modeled as lower-confidence
  (`CaptionConfidence.CANDIDATE`, never `CONFIRMED`) by design — per the
  milestone's own instruction, never to be presented as confirmed fact.
- `CaptionSource.EXTERNAL_METADATA` — reserved for a future external
  reference (e.g. a fan translation's own notes), not verified by this
  project.

## Category classification

`AudioCategory` (`VOICE_DIALOGUE`/`SOUND_EFFECT`/`AMBIENT_SOUND`/
`MUSIC`/`UNKNOWN_AUDIO`) exists as a real field, but only
`VOICE_DIALOGUE` is ever assigned by `caption_for_association()` itself
— the only category this project has live evidence for. `speaker` is a
modeled field (dialogue speaker name) but not yet populated: this
game's script format has real `speaker_name_start`/`speaker_name_end`
control codes (`CONTROL_A_MEANINGS`, already known), but correlating
them with a specific NAME (not just a boundary marker) was not
attempted this pass — real, scoped-out future work.

## Timing fields (Phase 16 groundwork, not rendered)

`start_offset_ms`/`end_offset_ms` exist on `AudioCaption` to keep the
data shape compatible with a future timed-subtitle system, per the
milestone's own forward-looking instruction. Neither is populated by
anything in this codebase yet — no subtitle rendering exists, and none
is implemented by this milestone.

## Runtime integration

`RuntimeVisualProvider.last_audio_caption`, computed once per `scan()`
(pure — no RAM access needed beyond what the script association already
captured). `RuntimeSnapshot.active_audio` entries carry a nested
`"caption"` object. The Visual Inspector's audio panel shows the
caption text (when `CONFIRMED`) with its source, or `UNKNOWN` — visually
distinct from the source/context lines above it, per the milestone's
own instruction never to blur the two.

## Tests

10 new tests in `tests/test_audio_caption.py`, including an explicit
regression that a caption is never confused with source identity (no
`source_file`/`xa_channel`-shaped fields on `AudioCaption` at all) and
that genuinely empty dialogue text stays `UNKNOWN` rather than becoming
a fabricated placeholder.
