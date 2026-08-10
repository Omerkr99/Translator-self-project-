# Custom Layout Descriptor — Formal Binary Specification

Version 1. Implemented by `gcrts.layout_descriptor`
(`encode_layout_descriptor`/`decode_layout_descriptor`); see
`TEXT_ENGINE_ARCHITECTURE.md` for how this fits into the wider Alternative
Text Engine plan. This spec is written before any MIPS code, per the master
prompt's section 12 requirement — nothing in this document depends on the
game-side consumer existing yet, and nothing here has been built for it.

## Purpose

A compact, bounded, easy-to-parse buffer an editor-controlled layout plan
(`gcrts.editor_layout_plan.EditorLayoutPlan`) serializes into, so that a
future MIPS-side renderer can draw explicit, editor-placed lines instead of
computing word wrap and position itself. The character stream at the end
uses the exact same 16-bit glyph codes `gcrts.script_encoder` already
produces, so that renderer can hand a line's slice straight to the game's
existing, already-proven glyph lookup/blit routine rather than needing a
second text representation.

## Endianness and alignment

Every multi-byte field is **little-endian** — the PS1's MIPS R3000 is
little-endian, so a future parser loads a field with a single `lw`/`lh`
instruction, no byte-swapping. Every multi-byte field in both the header
and each line record sits at an **even byte offset** — an unaligned MIPS
load either faults or costs extra instructions, so this is a hardware
constraint the format is built around, not a stylistic choice.

## Layout

```
+--------------------+
| Header (18 bytes)  |
+--------------------+
| Line record 0 (10) |
| Line record 1 (10) |
| ...                |
| Line record N-1     |
+--------------------+
| Character stream    |
| (2 bytes per code,  |
|  concatenated in    |
|  line order)        |
+--------------------+
```

### Header (18 bytes, format string `<4sHHHhhHBB`)

| Offset | Size | Field | Type | Meaning |
|---|---|---|---|---|
| 0 | 4 | `magic` | bytes | Always `b"CLD1"`. |
| 4 | 2 | `version` | uint16 | Format version. This spec is version `1`; a decoder must reject any other value rather than guess at a different layout. |
| 6 | 2 | `flags` | uint16 | Bit 0 = `paragraph_end`. Bits 1–15 reserved, must be 0. |
| 8 | 2 | `line_count` | uint16 | Number of line records that follow. Must be ≤ `MAX_LINES` (64). |
| 10 | 2 | `base_x` | int16 | First line's `x` (summary field; each line's own `x` is authoritative). |
| 12 | 2 | `base_y` | int16 | First line's `y` (summary field). |
| 14 | 2 | `line_height` | uint16 | `line[1].y - line[0].y` when ≥ 2 lines exist, else 0. A summary/convenience field, not authoritative — each line's own `y` is what actually places it. |
| 16 | 1 | `page_transition` | uint8 | `0` = wait_for_input, `1` = auto_continue, `2` = none. |
| 17 | 1 | `reserved` | uint8 | Must be `0`. A decoder must reject a nonzero value — it likely means the buffer isn't really a descriptor. |

### Line record (10 bytes each, format string `<HHhhBB`)

| Offset (from record start) | Size | Field | Type | Meaning |
|---|---|---|---|---|
| 0 | 2 | `start_char_index` | uint16 | Index into the character stream where this line's codes begin. |
| 2 | 2 | `char_count` | uint16 | Number of character codes this line owns. Must be ≤ `MAX_LINE_CHARS` (256). |
| 4 | 2 | `x` | int16 | The FINAL, already alignment-resolved screen-space X position -- see "Alignment resolution" below. Same coordinate space as the confirmed `base_X`/`max_width` constants in `gcrts.layout_validation`. |
| 6 | 2 | `y` | int16 | Screen-space Y position. |
| 8 | 1 | `alignment` | uint8 | `0` = left, `1` = center, `2` = right. Informational only -- see below. |
| 9 | 1 | `reserved` | uint8 | Must be `0`. |

Line records are addressed by fixed offset (`HEADER_SIZE + i * 10`), so a
parser never needs to walk variable-length data to find line `i`.

### Alignment resolution (resolved once, at encode time)

`x` is always the line's FINAL rendering position -- a consumer (whether
the reference Python decoder or a future MIPS parser) places glyphs
starting exactly there and does no alignment arithmetic of its own. This
is a deliberate design choice, not an oversight: earlier drafts of this
spec stored the editor's raw, pre-alignment `x` and left resolution to
the consumer, but the binary format has no per-line width-BUDGET field --
so a consumer with only these bytes would have nothing to center or
right-align WITHIN even if it tried. `gcrts.layout_descriptor.encode_layout_descriptor`
resolves this once, using the exact same width measurement
`gcrts.layout_validation.measure_pixel_width` provides (optionally with a
real `GlyphAtlas` for true glyph advance widths, falling back to the
project's standard character-count heuristic otherwise -- the same
optional-`atlas` convention every other function in this project uses):

```
left:   x = editor_x
center: x = editor_x + max(0, (budget - measured_width) // 2)
right:  x = editor_x + max(0, budget - measured_width)
```

where `budget` is the line's own `max_width_px` if the editor set one,
else `measured_width` itself (making alignment a no-op when no budget was
specified -- there's nothing to center or right-align within). The
`alignment` field is kept in the format regardless of this resolution,
purely as information for a human or editor reading the bytes back, not
because a correct consumer needs it to render.

### Character stream

`line_count` records' worth of `(start_char_index, char_count)` pairs
describe non-overlapping (in the reference implementation — nothing
technically prevents overlap, decoders should not assume otherwise)
slices of one shared array of uint16 glyph codes, immediately following
the last line record. Total length is `2 * max(start_char_index +
char_count)` bytes across all lines. Must not exceed `MAX_TOTAL_CHARS`
(4096) codes.

## Bounds (defensive limits, enforced by both encoder and decoder)

| Constant | Value | Enforced at |
|---|---|---|
| `MAX_LINES` | 64 | Encode (reject before producing bytes) and decode (reject a header's claim before trusting it) |
| `MAX_LINE_CHARS` | 256 | Same |
| `MAX_TOTAL_CHARS` | 4096 | Same |

These are NOT a claim about the confirmed, separate `MAX_VISIBLE_LINES = 4`
display limit in `gcrts.layout_validation` — that's how many lines the
real textbox shows at once; these are safety caps on the descriptor buffer
itself, sized generously above anything seen in this project so far.
Exceeding a bound is always an error (`DescriptorValidationError`), never
silent truncation, per the master prompt's explicit "do not truncate
silently" rule.

## Validation a decoder must perform, in order

1. Buffer is at least `HEADER_SIZE` (18) bytes.
2. `magic == b"CLD1"`.
3. `version == 1` (this version of the spec/decoder).
4. Header's `reserved` byte is `0`.
5. `line_count <= MAX_LINES`.
6. `page_transition` is one of the three known codes.
7. Buffer is at least `HEADER_SIZE + line_count * LINE_RECORD_SIZE` bytes
   (enough for every claimed line record).
8. For each line record: `reserved` byte is `0`; `char_count <=
   MAX_LINE_CHARS`; `alignment` is one of the three known codes.
9. The maximum `start_char_index + char_count` across all lines does not
   exceed `MAX_TOTAL_CHARS`.
10. Buffer is long enough to hold that many uint16 character codes after
    the line records.

Any failure raises `DescriptorValidationError` with a specific message —
never a silent fallback to zero/empty data, matching the master prompt's
"no memory region/behavior may be assumed safe without evidence" spirit
applied here to buffer contents instead of memory addresses.

## What this version deliberately does not cover

- No embedded font/atlas reference — the format assumes whatever glyph
  table is already live in the game, matching HOST_FITTED's own
  assumption today.
- No cross-descriptor references (e.g. "continue from descriptor at
  address X") — each descriptor is self-contained. Multi-page dialogue
  spanning more than `MAX_LINES` worth of content is out of this
  version's scope.
- No compression. Given `MAX_TOTAL_CHARS = 4096`, worst case is 8KB for
  the character stream alone — small enough on PS1 hardware that this
  wasn't judged worth the added parser complexity (see the master
  prompt's section 12: "minimal parser complexity" is an explicit design
  goal, traded off against size here).

A future version bump (`version = 2` etc.) must update both this document
and `gcrts.layout_descriptor.FORMAT_VERSION`, and the decoder must
continue to reject anything it doesn't recognize rather than guess.
