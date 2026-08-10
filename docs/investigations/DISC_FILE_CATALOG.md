# Disc File Catalog

The first genuinely new artifact produced while scoping the remaining
backlog (complex image formats, movies, audio, subtitles, persistent
build): a **complete** file listing of the actual disc, produced by
running the existing, already-proven `gcrts.iso9660` walker (read-only,
no PCSX-Redux needed) against the real disc image
(`C:\PCSXRedux\game\game.bin`, 636,488,832 bytes, single MODE2/2352 track
per `game.cue` — confirmed, not assumed). Every prior investigation in
this project worked from a handful of manually-discovered paths
(`DAT/CAP0/K0LINK.CDB`, `DAT/FONT/KFONT.CDB`, `DAT/SINKOU/MENUDAT.BIN`);
this is the first time the *entire* tree has been enumerated.

**A bug worth recording**: the one-off catalog script's own directory
filter missed the ISO9660 "parent directory" entry (raw name byte
`0x01`, distinct from the "self" entry `0x00`, which it did filter) —
recursing into `..` caused unbounded recursion and a crash. This was a
bug in the new script, not in `gcrts.iso9660` itself (that module only
returns directory records; it was never asked to auto-recurse before).
Fixed by filtering both `\x00` and `\x01` before recursing.

## Full listing (117 entries)

```
/CAP0.EXE;1                          391,168
/CAP1.EXE;1                          452,608
/CAP2.EXE;1                          434,176
/CAP3.EXE;1                          454,656
/CAP4.EXE;1                          454,656
/CAPX.EXE;1                          389,120
/MKUBI.EXE;1                         184,320
/MNINO.EXE;1                         184,320
/MOP.EXE;1                           184,320
/MOVER.EXE;1                         184,320
/MPRO.EXE;1                          184,320
/MRIKA.EXE;1                         184,320
/MYOKO.EXE;1                         184,320
/PROG.EXE;1                          221,184
/SLPS_001.02;1                        26,624
/SYSTEM.CNF;1                             68
/DUM.BIN;1                        31,227,648

/DAT/ALLCAP/CTLINK.CDB;1           3,581,952
/DAT/ALLCAP/KALINK.CDB;1              43,008
/DAT/CAP0/HAN.CDB;1                  335,872
/DAT/CAP0/K0LINK.CDB;1              2,701,312
/DAT/CAP1/K1LINK.CDB;1              4,857,856
/DAT/CAP1/S1C17E.CDB;1                28,672
/DAT/CAP1/SIN.CDB;1                  743,424
/DAT/CAP2/K2LINK.CDB;1              3,008,512
/DAT/CAP2/KOU.CDB;1                  522,240
/DAT/CAP3/K3LINK.CDB;1              4,493,312
/DAT/CAP3/S3C16.CDB;1                 94,208
/DAT/CAP3/YON.CDB;1                  569,344
/DAT/CAP4/K4LINK.CDB;1              1,865,728
/DAT/CAP4/NAN.CDB;1                  641,024
/DAT/CAP4/W4LINK.CDB;1              2,275,328
/DAT/CAPX/HIN.CDB;1                  397,312
/DAT/CAPX/KXLINK.CDB;1                475,136
/DAT/CAPX/WXLINK.CDB;1              1,546,240
/DAT/ENDING/ENDING.BIN;1              443,520
/DAT/FONT/KFONT.CDB;1                 602,112
/DAT/FONT1.TIM;1                        2,112
/DAT/HITO/AFRM.CDB;1                5,967,872
/DAT/HITO/SIKFORM.CDB;1             4,896,768
/DAT/LIFE/LMLINK.CDB;1                  4,096

/DAT/MOVIE/GAI.STR;1                3,160,064
/DAT/MOVIE/KIKU.STR;1               2,799,616
/DAT/MOVIE/KUBI.STR;1               5,371,904
/DAT/MOVIE/NINO.STR;1               4,012,032
/DAT/MOVIE/OP.STR;1                47,691,776
/DAT/MOVIE/PRO.STR;1               14,680,064
/DAT/MOVIE/YOKO.STR;1              27,105,280

/DAT/SINKOU/ALLLINK.CDB;1            477,184
/DAT/SINKOU/ICON1-3.TIM;1        192 each (x3)
/DAT/SINKOU/MEMDAT.BIN;1              32,021
/DAT/SINKOU/MENUDAT.BIN;1             30,318
/DAT/SINKOU/PROG.VB;1                499,520
/DAT/SINKOU/PROGDAT.BIN;1             69,663
/DAT/SINKOU/PROGHEAD.CDB;1            20,480
/DAT/SINKOU/PROGVAB.CDB;1            514,048

/DAT/XA1/XAPACK00-29.BIN;1   (30 files, 104,153,088 down to 2,375,680 bytes, descending)
/DAT/XA2/XAPACK30-42.BIN;1   (13 files, 3,424,256 down to 1,523,712 bytes, descending)
```

(Full per-file LBA is in the raw scan output; omitted here for brevity —
re-run is one line: `gcrts.iso9660.read_root_directory`/`read_directory`
against `game.bin`, already exercised by this session's script.)

## What this directly answers

- **Movies exist, unambiguously**: `DAT/MOVIE/` holds 7 `.STR` files,
  ~105MB total. `OP.STR` at 47.7MB is almost certainly the opening movie
  (openings are conventionally the largest single video asset). Prior to
  this catalog, Stage B's own audit found *zero* evidence movies existed
  on this disc at all — this replaces "unknown, not even searched" with
  "confirmed present, here are the exact files."
- **Streaming audio very likely exists**: 43 `XAPACK*.BIN` files across
  `DAT/XA1/`/`DAT/XA2/`, ~230MB combined, numbered sequentially and
  strictly decreasing in size — the naming and shape strongly suggest
  packed XA-ADPCM streaming audio chunks (this game's own `.STR` movies
  already use XA-interleaved audio per the standard PS1 convention, and a
  visual-novel-style game with per-location "voice" labels already
  cataloged in MENUDAT — `sound.sculpture_hall`, `sound.koube_bridge`,
  etc. — needs a streaming audio source for exactly this kind of content).
  Not yet confirmed by parsing a single sector.
- **A second, different-shaped audio candidate**: `DAT/SINKOU/PROG.VB`
  (487KB) plus `PROGHEAD.CDB` (20KB) plus `PROGVAB.CDB` (502KB), all
  living next to `PROGDAT.BIN`/`MENUDAT.BIN` — i.e. owned by the menu
  executable, not a chapter. `.VB` is the standard Sony PS1 extension for
  a **VAB body** (sample data); a same-named `.VH`/header is conventional
  but absent here -- `PROGHEAD.CDB`'s size and position make it a
  plausible substitute, and `PROGVAB.CDB` may be a self-contained
  combined form. This shape (small, menu-owned, VAB-like) fits UI sound
  effects/music far better than streaming voice — a DIFFERENT sound
  system from the XAPACK files, not a duplicate lead.
- **Animation/complex-image candidates for Stage A**: `DAT/HITO/AFRM.CDB`
  (5.97MB) and `SIKFORM.CDB` (4.9MB) are large `.CDB` files outside every
  already-solved format (not a chapter script, not KFONT, not
  MENUDAT/PROGDAT TIM data). `AFRM.CDB` was already extracted byte-exact
  in a prior session (`C:\PCSXRedux\afrm_full.bin`, confirmed identical
  size) but never parsed past extraction — no doc describes its internal
  structure. This is the leading candidate location for SDB2.0/SDB2.2/
  MS4/GP4 content, though nothing here confirms it yet.
- **No standalone SDB/MS4/GP4-named files anywhere on the disc** — these
  are payload formats that would have to live embedded inside one of the
  `.CDB` containers above (most plausibly `AFRM.CDB`/`SIKFORM.CDB`, or
  one of the per-chapter `K#LINK.CDB` files), not top-level disc files
  with those extensions. Consistent with (not contradicting) the earlier
  finding that MENUDAT/PROGDAT specifically hold ordinary TIM data.
