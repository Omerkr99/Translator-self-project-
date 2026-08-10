from gcrts.render_mode import RenderMode, RuntimePatchState, RuntimePatchStatus


def test_render_mode_has_exactly_the_three_master_prompt_modes():
    assert {m.value for m in RenderMode} == {"original", "host_fitted", "custom_engine"}


def test_runtime_patch_status_has_the_six_named_milestones():
    assert {s.value for s in RuntimePatchStatus} == {
        "text_buffer_ready",
        "text_buffer_injected",
        "engine_patch_ready",
        "engine_patch_installed",
        "layout_descriptor_injected",
        "live_render_validated",
    }


def test_runtime_patch_state_defaults_to_all_false():
    state = RuntimePatchState()
    d = state.to_dict()
    assert all(v is False for v in d.values())


def test_runtime_patch_state_tracks_milestones_independently():
    # A text buffer can be injected with no engine patch installed at all --
    # this is the whole reason it's several booleans, not one enum.
    state = RuntimePatchState(text_buffer_ready=True, text_buffer_injected=True)
    assert state.text_buffer_injected is True
    assert state.engine_patch_installed is False


def test_runtime_patch_state_roundtrips_through_dict():
    state = RuntimePatchState(
        text_buffer_ready=True,
        text_buffer_injected=True,
        engine_patch_ready=True,
        engine_patch_installed=False,
        layout_descriptor_injected=False,
        live_render_validated=False,
    )
    restored = RuntimePatchState.from_dict(state.to_dict())
    assert restored == state


def test_runtime_patch_state_from_dict_defaults_missing_keys_false():
    # A dict from before a milestone existed must not crash and must
    # default that milestone to False.
    restored = RuntimePatchState.from_dict({"text_buffer_injected": True})
    assert restored.text_buffer_injected is True
    assert restored.live_render_validated is False
