# MENUDAT Asset Catalog

All assets currently shown in the Asset Browser come from the single canonical
disc file `DAT/SINKOU/MENUDAT.BIN;1` (30,318 bytes). It contains 32 consecutive
game-compressed standard TIM sprites. Every entry below is 4bpp indexed with a
16-entry BGR555/STP CLUT and uses `EXACT_CONSUMED_SIZE` until a relocatable
container layout is independently proven.

Clicking any card opens that exact block directly. All 32 can currently be
decoded, inspected, exported, palette-preservingly replaced, edited with the
indexed text helper, exact-size validated, rebuilt into a working copy and
temporarily tested in PCSX-Redux. Canonical `MENUDAT.BIN` is never overwritten.

| Block | Meaning | Usage | Offset | Compressed | Dimensions | Direct access |
|---:|---|---|---:|---:|---:|---|
| 0 | View Spoils (`戦利品を見る`) | System menu | `0x0000` | 687 | 160x16 | YES — click block 0 |
| 1 | Window Color (`ウィンドーカラー`) | System menu | `0x02AF` | 634 | 160x16 | YES — click block 1 |
| 2 | Return to Title (`タイトルに戻る`) | System menu | `0x0529` | 648 | 108x20 | YES — click block 2 |
| 3 | Rumor 1 — Spirit-photo Park | Chapter title | `0x07B1` | 1,405 | 240x16 | YES — click block 3 |
| 4 | Rumor 2 — Music Room M.F. | Chapter title | `0x0D2E` | 1,146 | 240x16 | YES — click block 4 |
| 5 | Rumor 3 — Last Train | Chapter title | `0x11A8` | 1,009 | 240x16 | YES — click block 5 |
| 6 | Rumor 4 — Seven Mysteries of Hinashiro High | Chapter title | `0x1599` | 1,595 | 240x16 | YES — click block 6 |
| 7 | Start (`開始`) | Main-menu button | `0x1BD4` | 514 | 100x24 | YES; edit/injection LIVE VERIFIED |
| 8 | Prepare (`準備`) | Main-menu button | `0x1DD6` | 498 | 100x24 | YES; edit/injection LIVE VERIFIED |
| 9 | Photos (`『写真』`) | Category label | `0x1FC8` | 617 | 64x32 | YES — click block 9 |
| 10 | Park — Koube Bridge | Photo/location label | `0x2231` | 815 | 132x16 | YES — click block 10 |
| 11 | Park — In Front of Toilet | Photo/location label | `0x2560` | 877 | 148x16 | YES — click block 11 |
| 12 | Park — Midnight Great Torii | Photo/location label | `0x28CD` | 1,231 | 180x16 | YES — click block 12 |
| 13 | Park — Parking Lot | Photo/location label | `0x2D9C` | 802 | 120x16 | YES — click block 13 |
| 14 | M Station — Women's Toilet | Photo/location label | `0x30BE` | 1,048 | 160x16 | YES — click block 14 |
| 15 | M Station — Men's Toilet | Photo/location label | `0x34D6` | 1,061 | 160x16 | YES — click block 15 |
| 16 | M Station — Connecting Walkway | Photo/location label | `0x38FB` | 976 | 132x16 | YES — click block 16 |
| 17 | M Station — Soba Shop | Photo/location label | `0x3CCB` | 1,249 | 180x16 | YES — click block 17 |
| 18 | M Station — Platform 3 | Photo/location label | `0x41AC` | 1,186 | 180x16 | YES — click block 18 |
| 19 | M Station — Vending Machine | Photo/location label | `0x464E` | 1,177 | 168x16 | YES — click block 19 |
| 20 | M Station — Platform 4 | Photo/location label | `0x4AE7` | 1,169 | 180x16 | YES — click block 20 |
| 21 | M Station — Yuyamigaoka-bound | Photo/location label | `0x4F78` | 1,247 | 180x16 | YES — click block 21 |
| 22 | Hinashiro High — Gym Equipment Room | Photo/location label | `0x5457` | 1,358 | 180x16 | YES — click block 22 |
| 23 | Town View from Waterworks | Photo/location label | `0x59A5` | 1,071 | 144x16 | YES — click block 23 |
| 24 | Live Recordings (`『生録』`) | Category label | `0x5DD4` | 613 | 64x32 | YES — click block 24 |
| 25 | Voice in Sculpture Hall | Sound label | `0x6039` | 662 | 84x16 | YES — click block 25 |
| 26 | Voice at Koube Bridge | Sound label | `0x62CF` | 671 | 100x16 | YES — click block 26 |
| 27 | Midnight School Broadcast | Sound label | `0x656E` | 1,043 | 132x16 | YES — click block 27 |
| 28 | Midnight Piano | Sound label | `0x6981` | 797 | 112x16 | YES — click block 28 |
| 29 | Voice in Library | Sound label | `0x6C9E` | 630 | 80x16 | YES — click block 29 |
| 30 | Voice in Air-raid Shelter | Sound label | `0x6F14` | 652 | 84x16 | YES — click block 30 |
| 31 | Park — Midday Great Torii | Photo/location label | `0x71A0` | 1,230 | 180x16 | YES — click block 31 |

## What “direct access” means today

### Implemented now

- Click a card to resolve directly to disc file, block, compressed offset and size.
- Inspect the decoded sprite and its exact 16-color CLUT.
- See raw BGR555/STP values and per-index usage.
- Export the individual block to a transparent PNG.
- Replace it with a same-size PNG using only representable palette colors.
- Clear and write local English text using an existing palette index.
- See raw compressed size, required exact size and safe/blocked status.
- Build a complete modified MENUDAT working copy without altering other slots.
- Send the complete working copy as a temporary PCSX-Redux patch.
- Restore the selected in-memory edit or clear emulator patches explicitly.

### Screen mapping

Blocks 7 and 8 have initial manually verified native-screen mappings:

- Start: approximately `(65,200,100,24)`
- Prepare: approximately `(160,200,100,24)`

The descriptor stores these mappings, but the screenshot rectangle overlay and
click-the-game-screen picker are not implemented yet. Therefore direct access
currently begins from the Asset Browser cards, not by clicking the live game.

### Runtime selection color

The successful screenshot proves both replacement labels change between dark
and red/pink as selection moves. The fact of runtime color-state behavior is
`LIVE_OBSERVED`; whether it is alternate CLUT upload or GPU primitive RGB
modulation remains `UNKNOWN` and is not claimed as solved.

## Confidence note

The block boundaries, dimensions, formats, offsets and Start/Prepare meanings
are binary/live verified. The remaining English descriptions are semantic
translations of the visible Japanese labels in the decoded contact sheet. They
describe the UI text, not yet a proven screen occurrence for every block.
