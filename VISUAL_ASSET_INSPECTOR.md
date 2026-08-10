# Visual Asset & Text Inspector

The Visual Inspector makes the captured game screen the navigation surface for GCRTS. It merges verified disc assets, runtime text, candidates, and unknown regions into one list of `InspectableScreenObject` values.

Run it from the project root:

```powershell
python -m gcrts.visual_inspector_ui --registry screen_mappings.json --asset-source sdb_main_menu_asset/MENUDAT.BIN
```

`Capture Current Screen` reads the configured 320x240 VRAM region from PCSX-Redux's web API. `Load Screenshot` is the offline alternative. The selected `ScreenContext` controls which mappings may appear.

For the verified main-menu context, START and SETTINGS/PREPARE are outlined automatically. Hover reports their representation, source block, and confidence. Clicking and choosing `Open Correct Inspector` opens the existing Asset Inspector directly at MENUDAT block 7 or 8.

Mapping Mode lets the user drag a rectangle, associate it with a known object ID or preserve it as unknown, and save it to the registry. `LIVE_VERIFIED` entries are protected from weaker replacement and deletion.

Current milestone limitation: screen identity is selected by context, not automatically detected. Renderer 1 has a safe object/dispatch contract but no live line collector in this viewer yet. Renderer 2 is intentionally details-only.
