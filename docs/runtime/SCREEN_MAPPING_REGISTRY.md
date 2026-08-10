# Screen Mapping Registry

`screen_mappings.json` is the human-readable persistent registry. It stores `ScreenContext` records and objects scoped to each context, preventing main-menu rectangles from appearing in unrelated scenes.

The initial verified context is `twilight.main_menu` at 320x240. It contains:

| Object | Bounds | Source | Confidence |
|---|---:|---|---|
| Start | 65,200,100,24 | `DAT/SINKOU/MENUDAT.BIN;1`, block 7 | LIVE_VERIFIED |
| Prepare / Settings | 160,200,100,24 | `DAT/SINKOU/MENUDAT.BIN;1`, block 8 | LIVE_VERIFIED |

Manual mappings persist immediately. CRUD and hit testing are implemented. A lower-confidence mapping cannot replace a `LIVE_VERIFIED` object, and the UI protects verified entries from deletion.

Only objects with known screen bounds belong here. The remaining MENUDAT catalog is not sprayed over the screen without positional evidence.
