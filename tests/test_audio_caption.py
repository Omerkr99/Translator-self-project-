from gcrts.audio_caption import (
    AudioCaption,
    AudioCategory,
    CaptionConfidence,
    CaptionSource,
    caption_for_association,
    create_manual_caption,
    create_user_caption,
)
from gcrts.script_audio_association import SOUND_OR_VOICE_CUE_SUBTYPE, ScriptAssociationConfidence, ScriptAudioAssociation


def _association(
    dialogue_text="hello there",
    control_code_type=SOUND_OR_VOICE_CUE_SUBTYPE,
    confidence=ScriptAssociationConfidence.SCRIPT_CONTEXT_RESOLVED,
) -> ScriptAudioAssociation:
    return ScriptAudioAssociation(
        association_id="a",
        script_source="live_ram",
        script_unit_id="live_line_00",
        script_unit_start=0,
        script_unit_end=10,
        script_cursor=5,
        control_code_offset=1,
        control_code_type=control_code_type,
        control_code_raw_low_byte=25,
        raw_parameter=127,
        dialogue_text=dialogue_text,
        buffer_fingerprint="abc123",
        audio_event=None,
        confidence=confidence,
    )


# --- caption_for_association -- the only self-sourced caption path ---------


def test_caption_for_association_confirmed_voice_dialogue():
    assoc = _association(dialogue_text="Don't go.")
    cap = caption_for_association(assoc, caption_id="cap1")
    assert cap.audio_category == AudioCategory.VOICE_DIALOGUE
    assert cap.caption_text == "Don't go."
    assert cap.caption_source == CaptionSource.SCRIPT_CONTEXT
    assert cap.confidence == CaptionConfidence.CONFIRMED
    assert cap.stable_key == assoc.stable_key


def test_caption_for_association_unknown_when_association_none():
    cap = caption_for_association(None, "cap1")
    assert cap.audio_category == AudioCategory.UNKNOWN_AUDIO
    assert cap.caption_text is None
    assert cap.caption_source == CaptionSource.UNKNOWN
    assert cap.confidence == CaptionConfidence.UNKNOWN


def test_caption_for_association_unknown_when_association_unresolved():
    assoc = _association(confidence=ScriptAssociationConfidence.SCRIPT_CONTEXT_UNKNOWN)
    cap = caption_for_association(assoc, "cap1")
    assert cap.caption_text is None
    assert cap.confidence == CaptionConfidence.UNKNOWN


def test_caption_for_association_unknown_for_non_sound_control_code():
    """Never fabricated for a control code this project has no evidence
    is audio-related at all."""
    assoc = _association(control_code_type=0x0100)  # speaker_name_char, not sound_or_voice_cue
    cap = caption_for_association(assoc, "cap1")
    assert cap.caption_text is None
    assert cap.caption_source == CaptionSource.UNKNOWN


def test_caption_for_association_unknown_when_dialogue_text_empty():
    """Never invents placeholder text when there's genuinely nothing to
    show -- an empty/whitespace-only dialogue_text stays UNKNOWN, not a
    fabricated caption."""
    assoc = _association(dialogue_text="   ")
    cap = caption_for_association(assoc, "cap1")
    assert cap.caption_text is None
    assert cap.confidence == CaptionConfidence.UNKNOWN


def test_caption_never_confused_with_source_identity():
    """A caption never claims to know WHERE audio comes from -- that's
    AudioAsset/RuntimeAudioEvent's job, not AudioCaption's."""
    assoc = _association()
    cap = caption_for_association(assoc, "cap1")
    assert not hasattr(cap, "source_file")
    assert not hasattr(cap, "xa_channel")


# --- manual / user captions (never auto-invoked with invented text) --------


def test_create_manual_caption_is_confirmed_and_manual_listening_sourced():
    cap = create_manual_caption("cap2", "door creaks", AudioCategory.SOUND_EFFECT, stable_key="k1")
    assert cap.caption_text == "door creaks"
    assert cap.audio_category == AudioCategory.SOUND_EFFECT
    assert cap.caption_source == CaptionSource.MANUAL_LISTENING
    assert cap.confidence == CaptionConfidence.CONFIRMED
    assert cap.stable_key == "k1"


def test_create_user_caption_is_user_defined():
    cap = create_user_caption("cap3", "corrected translation", AudioCategory.VOICE_DIALOGUE, speaker="Rika")
    assert cap.caption_source == CaptionSource.USER_DEFINED
    assert cap.speaker == "Rika"
    assert cap.confidence == CaptionConfidence.CONFIRMED


# --- to_dict / from_dict round trip -----------------------------------------


def test_caption_round_trips_through_dict():
    assoc = _association()
    cap = caption_for_association(assoc, "cap1")
    restored = AudioCaption.from_dict(cap.to_dict())
    assert restored == cap


def test_manual_caption_round_trips_through_dict():
    cap = create_manual_caption("cap2", "footsteps approaching", AudioCategory.AMBIENT_SOUND)
    restored = AudioCaption.from_dict(cap.to_dict())
    assert restored == cap
