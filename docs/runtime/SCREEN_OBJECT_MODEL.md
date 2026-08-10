# Screen Object Model

`gcrts.screen_objects` defines one model for everything visible on screen:

- object types: image, composite image, runtime text, UI text asset, unknown texture/text/region;
- native screen bounds and hit testing;
- source evidence and editor target;
- confidence: `LIVE_VERIFIED`, `MANUAL_VERIFIED`, `STATIC_CONFIRMED`, `HIGH_CONFIDENCE`, `CANDIDATE`, or `UNKNOWN`;
- text representation and translation status.

The central distinction is evidence-based, not appearance-based:

- `RASTER_TEXT_ASSET`: pixels stored in an asset, such as MENUDAT block 7 START. It routes to Asset Inspector.
- `RUNTIME_TEXT_RENDERER_1`: glyphs generated at runtime. It routes to Text/Layout Inspector only when its runtime profile validates.
- `RUNTIME_TEXT_RENDERER_2`: detected research candidate. It is visible but not editable.
- `UNKNOWN_TEXT`: no verified source; no silent guess is made.

An invalid/stale Renderer 1 profile creates a non-editable object with `UNKNOWN` confidence. Static asset inspection remains available independently.
