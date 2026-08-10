"""Audio Captions -- a semantic "what is being heard" layer, deliberately
separate from `AudioAsset` identity (`gcrts.xa_disc_index`/
`gcrts.runtime_audio`, "where does this audio come from") and from
`ScriptAudioAssociation` (`gcrts.script_audio_association`, "which
script occurrence triggered it"). A caption answers a THIRD, different
question -- what a human would perceive listening to it -- and this
module is careful never to conflate the three.

Only ONE caption source is implemented here as something this project
can produce on its own, honestly: `CaptionSource.SCRIPT_CONTEXT` for
`AudioCategory.VOICE_DIALOGUE`, using the real, already-decoded dialogue
text (`ScriptAudioAssociation.dialogue_text`) as the caption. This is
genuine evidence, not an inference -- it's the literal text the game
displays on screen while that audio plays, extracted by
`gcrts.script_decoder`, not guessed at.

Every other caption source this module models
(`MANUAL_LISTENING`, `MODEL_INFERRED`, `EXTERNAL_METADATA`,
`USER_DEFINED`) requires either a human who has actually heard the
audio, or a real classification model -- NEITHER of which this module
(or the environment it runs in) has access to. `create_manual_caption`/
`create_user_caption` exist so a human operator (or a future model
integration) CAN attach one, but nothing in this codebase calls them
with invented text. Per this project's own standing rule against
fabricated content: no non-dialogue caption text (e.g. a made-up
"[door creaks]") is ever attached to a real captured event by this
module itself -- `caption_for_association` returns `caption_text=None`,
`caption_source=CaptionSource.UNKNOWN` for anything it cannot honestly
source from real evidence, rather than inventing something plausible.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AudioCategory(str, Enum):
    VOICE_DIALOGUE = "VOICE_DIALOGUE"
    SOUND_EFFECT = "SOUND_EFFECT"
    AMBIENT_SOUND = "AMBIENT_SOUND"
    MUSIC = "MUSIC"
    UNKNOWN_AUDIO = "UNKNOWN_AUDIO"


class CaptionSource(str, Enum):
    USER_DEFINED = "USER_DEFINED"  # a human explicitly typed/confirmed this
    SCRIPT_CONTEXT = "SCRIPT_CONTEXT"  # derived from real decoded script data (e.g. dialogue text) -- evidence, not a guess
    MANUAL_LISTENING = "MANUAL_LISTENING"  # a human actually listened to the audio and described it
    EXTERNAL_METADATA = "EXTERNAL_METADATA"  # from an external reference (e.g. a fan translation's own notes), not verified by this project
    MODEL_INFERRED = "MODEL_INFERRED"  # produced by an audio classification model -- never to be presented as fact
    UNKNOWN = "UNKNOWN"  # no caption available yet


class CaptionConfidence(str, Enum):
    CONFIRMED = "CONFIRMED"  # backed by real evidence (decoded game text, or a human's direct confirmation)
    CANDIDATE = "CANDIDATE"  # plausible but not verified -- e.g. MODEL_INFERRED output
    UNKNOWN = "UNKNOWN"


@dataclass
class AudioCaption:
    caption_id: str
    audio_category: AudioCategory
    caption_text: str | None  # None when genuinely unresolved -- never a placeholder/invented string
    speaker: str | None
    caption_source: CaptionSource
    confidence: CaptionConfidence
    stable_key: str | None  # gcrts.script_audio_association.ScriptAudioAssociation.stable_key this attaches to, if any
    start_offset_ms: float | None  # reserved for future timed-subtitle use (Phase 16 groundwork) -- not rendered anywhere yet
    end_offset_ms: float | None

    def to_dict(self) -> dict:
        return {
            "caption_id": self.caption_id,
            "audio_category": self.audio_category.value,
            "caption_text": self.caption_text,
            "speaker": self.speaker,
            "caption_source": self.caption_source.value,
            "confidence": self.confidence.value,
            "stable_key": self.stable_key,
            "start_offset_ms": self.start_offset_ms,
            "end_offset_ms": self.end_offset_ms,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AudioCaption":
        return cls(
            caption_id=d["caption_id"],
            audio_category=AudioCategory(d.get("audio_category", "UNKNOWN_AUDIO")),
            caption_text=d.get("caption_text"),
            speaker=d.get("speaker"),
            caption_source=CaptionSource(d.get("caption_source", "UNKNOWN")),
            confidence=CaptionConfidence(d.get("confidence", "UNKNOWN")),
            stable_key=d.get("stable_key"),
            start_offset_ms=d.get("start_offset_ms"),
            end_offset_ms=d.get("end_offset_ms"),
        )


def _unknown_caption(caption_id: str, stable_key: str | None) -> AudioCaption:
    return AudioCaption(
        caption_id=caption_id,
        audio_category=AudioCategory.UNKNOWN_AUDIO,
        caption_text=None,
        speaker=None,
        caption_source=CaptionSource.UNKNOWN,
        confidence=CaptionConfidence.UNKNOWN,
        stable_key=stable_key,
        start_offset_ms=None,
        end_offset_ms=None,
    )


def caption_for_association(association, caption_id: str = "current") -> AudioCaption:
    """Pure function -- `association` is a
    `gcrts.script_audio_association.ScriptAudioAssociation`. The ONLY
    case this can honestly produce non-UNKNOWN output for is a resolved
    association whose owning script unit has real dialogue text and
    whose raw control code is `sound_or_voice_cue` (subtype `0x0800`,
    the one control code this project has confirmed, via Stage C's own
    sector-level decode of mono 4-bit XA-ADPCM, is used for spoken
    lines) -- everything else genuinely has no evidence to build a
    caption from, so it stays UNKNOWN rather than guessing at a sound
    effect or ambience description this project has no way to verify
    (no audio playback/listening capability, no classifier integrated).
    """
    from gcrts.script_audio_association import SOUND_OR_VOICE_CUE_SUBTYPE, ScriptAssociationConfidence

    if association is None or association.confidence != ScriptAssociationConfidence.SCRIPT_CONTEXT_RESOLVED:
        return _unknown_caption(caption_id, association.stable_key if association else None)

    if association.control_code_type != SOUND_OR_VOICE_CUE_SUBTYPE:
        return _unknown_caption(caption_id, association.stable_key)

    text = (association.dialogue_text or "").strip()
    if not text:
        return _unknown_caption(caption_id, association.stable_key)

    return AudioCaption(
        caption_id=caption_id,
        audio_category=AudioCategory.VOICE_DIALOGUE,
        caption_text=text,
        speaker=None,  # speaker-name control codes exist (CONTROL_A_MEANINGS: speaker_name_start/end) but are not yet correlated here -- real future work, not guessed at
        caption_source=CaptionSource.SCRIPT_CONTEXT,
        confidence=CaptionConfidence.CONFIRMED,
        stable_key=association.stable_key,
        start_offset_ms=None,
        end_offset_ms=None,
    )


def create_manual_caption(
    caption_id: str,
    text: str,
    audio_category: AudioCategory,
    stable_key: str | None = None,
    speaker: str | None = None,
) -> AudioCaption:
    """For a human operator who has actually listened to the audio and
    is describing what they heard -- e.g. "[door creaks]". Never called
    with invented text by this codebase itself; exists for a real
    operator (or a future, explicitly-integrated audio review workflow)
    to use."""
    return AudioCaption(
        caption_id=caption_id,
        audio_category=audio_category,
        caption_text=text,
        speaker=speaker,
        caption_source=CaptionSource.MANUAL_LISTENING,
        confidence=CaptionConfidence.CONFIRMED,
        stable_key=stable_key,
        start_offset_ms=None,
        end_offset_ms=None,
    )


def create_user_caption(
    caption_id: str,
    text: str,
    audio_category: AudioCategory,
    stable_key: str | None = None,
    speaker: str | None = None,
) -> AudioCaption:
    """A user-entered/confirmed caption via the UI (Phase 13) -- kept
    distinct from MANUAL_LISTENING (which specifically means "someone
    listened to verify this") since a user-entered caption might instead
    be a corrected translation or an edited version of a SCRIPT_CONTEXT
    caption."""
    return AudioCaption(
        caption_id=caption_id,
        audio_category=audio_category,
        caption_text=text,
        speaker=speaker,
        caption_source=CaptionSource.USER_DEFINED,
        confidence=CaptionConfidence.CONFIRMED,
        stable_key=stable_key,
        start_offset_ms=None,
        end_offset_ms=None,
    )
