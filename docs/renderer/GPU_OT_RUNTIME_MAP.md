# GPU / Ordering-Table Runtime Map

Milestone 3 of the post-audit development workflow: cross-check whether
Renderer 1's proven primitive-submission chain and the Runtime Asset
Tracker's 4 known OT roots are the same table, overlapping tables, or
genuinely separate systems -- and document the full source-object ->
primitive -> OT -> GPU chain for both, with every link tagged by how it
was actually verified.

## Result up front: two separate, non-overlapping systems (Definition of Done option B)

They are **not** the same table, and forcing them into one model would be
wrong. Confirmed live, this session, both directions:

- Renderer 1's `addPrim` (`0x800774B4`) never inserts into any of the 4
  known PROG.EXE OT roots (`0x80076A24`, `0x80076A64`, `0x80075770`,
  `0x800757B0`) -- captured 25 real `addPrim` hits during an active
  dialogue scene and every single `$a0` (the OT-bucket argument) was one
  of 4 completely different addresses (`0x800BBDFC`, `0x800BBE04`,
  `0x800D0A54`, `0x800D34A0`), zero overlap.
- `addPrim` (`0x800774B4`) is never called at all while PROG.EXE (the
  menu) is loaded -- armed for 60+ seconds against a live main-menu scene
  that was independently confirmed (via the Milestone 2 tracker-backed
  scan, run immediately before and after) to be drawing 3 real assets
  every frame, and got zero hits. Reading `0x800774B4` directly under
  PROG.EXE returns `00 00 00 00 00 00 00 06 00 00 00 30 00 00 00 00` --
  not valid code at all, versus a real `lui`/`ori` prologue under the
  dialogue-scene overlay. This is this project's well-established
  overlay-drift phenomenon, now confirmed for this specific address pair.

The reason is structural, not a bug: the two systems belong to two
different loaded executables that are never simultaneously resident.
Renderer 1 (`addPrim` at `0x800774B4`) runs under the narrative/dialogue
overlay family; the Runtime Asset Tracker's 4 roots are specifically
validated against `PROG.EXE` (the main-menu executable) and are only
meaningful while it is loaded. They were never expected to be the same
table once stated this way -- this milestone's job was to check that
directly rather than assume it, and the direct check confirms it.

## System A: Renderer 1 (narrative/dialogue overlays)

```
position record ($s1, 14 bytes, X/Y at +0x8/+0xa)      [LIVE_VERIFIED -- RENDERER_LIVE_PROOF.md secs 10-12]
  -> sh into primitive buffer ($s0, 40-byte POLY_FT4)   [LIVE_VERIFIED -- sec 10]
    -> addPrim(a0=OT bucket, a1=primitive)              [LIVE_VERIFIED -- sec 13 confirmed a1 is shared/generic;
                                                           a0 (which bucket) captured for the first time THIS milestone]
      -> OT bucket cursor, one of several                [LIVE_VERIFIED this milestone -- see buckets below]
        -> DrawOTag -> GPU                               [PARTIAL -- inherited from the pre-existing "addPrim links
                                                           by reference" static finding; DrawOTag itself not re-traced]
```

Buckets observed live this session (dialogue scene, `SLPS00102.sstate7`,
25 consecutive `addPrim` hits, ~5 seconds real time):

| `$a0` (OT bucket) | `$a1` values seen | Interpretation |
|---|---|---|
| `0x800BBDFC` | `0x800BEB60`, `0x800BEB88` | full-screen background quads (matches sec 13's earlier finding) |
| `0x800BBE04` | `0x800BEC00`, `0x800BEC28` | a second background/composite layer |
| `0x800D0A54` | `0x800D0A5C`, `0x800D0A84`, ... `0x800D0D2C` (14 entries, `+0x28` stride) | the dialogue text line -- confirmed by exact match to the known double-buffered text-primitive destination from section 11 |
| `0x800D34A0` | `0x800D325C`, `0x800A3A1C` | a fourth primitive class, not yet identified (possibly the advance-cursor `▼` or a portrait layer) |

Note the text bucket (`0x800D0A54`) sits exactly 8 bytes before its own
first primitive (`0x800D0A5C`) -- consistent with a small, renderer-local
"current OT tail" variable dedicated to that primitive stream, not a
large fixed table. This is a genuinely different OT-management style from
PROG.EXE's (below), not just a different address.

## System B: PROG.EXE (main menu / photos-spoils menu)

```
MENUDAT/PROGDAT decoded asset in VRAM                    [LIVE_VERIFIED -- gcrts.vram_asset_detector, Milestone 2]
  -> ??? primitive construction (not addPrim)             [UNKNOWN -- addPrim ruled out this milestone, real
                                                           mechanism not identified]
    -> OT root write at 0x80049650                        [STATIC_CONFIRMED -- earlier session's disassembly;
                                                           re-read live this session, byte-identical]
      -> GPU DMA trigger at 0x80049670                     [STATIC_CONFIRMED -- earlier session's disassembly,
                                                           not re-traced live this session]
        -> one of 4 known roots (0x80076A24/A64/0x75770/0x757B0) [LIVE_VERIFIED -- Milestone 2's tracker-backed
                                                           scan correlates real primitives through these roots
                                                           to real VRAM assets every scan]
          -> DrawOTag -> GPU                               [PARTIAL -- not re-traced this session]
```

`addPrim` is definitively ruled OUT as PROG.EXE's submission mechanism
(see above). A plausible, UNCONFIRMED explanation, offered as a hypothesis
only: PROG.EXE's menu composition is largely static per screen (same
background + button labels every frame, unlike Renderer 1's
character-by-character dialogue text), so it may submit a precomputed,
fixed primitive chain via a one-time-per-frame root write + DMA rather
than a per-primitive linking call the way Renderer 1 does. This was not
independently confirmed by disassembly this session and should be treated
as PARTIAL / a lead, not a finding.

## What this settles for later milestones

- Milestone 4/5 (Global Selection / Visual Inspector) can safely treat
  Renderer 1 and the Runtime Asset Tracker as two independent live-object
  sources that are never both non-empty at the same moment (one implies
  the other's OT roots are meaningless right now) -- no merge/dedup logic
  between their outputs is needed at the OT level, only at the UI/
  selection level.
- The open item for a future session, if PROG.EXE's own primitive-
  construction step ever needs to be edited/patched directly (as opposed
  to today's working approach of editing decoded VRAM/disc assets):
  identify what actually builds PROG.EXE's primitive chain, since it is
  confirmed not to be `0x800774B4`.
