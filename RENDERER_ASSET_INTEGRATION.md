# Renderer and Asset Integration

The integration boundary is `InspectableScreenObject -> dispatch()`:

- image and UI text assets -> existing Asset Inspector;
- Renderer 1 runtime text -> Text/Layout Inspector when `profile_valid` is true;
- Renderer 2 candidate -> investigation details, editing unavailable;
- unknown -> mapping/investigation path.

Existing MENUDAT/TIM/CLUT/edit/re-encode/temporary-injection functionality is reused rather than duplicated. Renderer 1 knowledge is represented without embedding stale absolute addresses. Its proven glyph/layout pipeline and CLD1 work remain the basis for the next collector milestone, but the current viewer does not claim live line discovery yet.

Renderer 2 support is deliberately honest: candidates can be classified and shown, but no editing action is exposed. GPU-assisted point-to-primitive resolution remains deferred until manual mappings and runtime collection are stable.
