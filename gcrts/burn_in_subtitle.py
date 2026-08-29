"""Burns subtitle text directly onto a decoded video frame's pixels --
the actual deliverable-shaped half of movie subtitles, per the user's
own explicit correction (2026-08-26, see the `project-fandub-goal`
memory entry): the finished translation has to survive being burned to
a real CD and played on real PS1 hardware, which can never run this
project's host-side Python tooling. `gcrts.subtitle_track_runner`'s
`ExternalOverlayRenderer` path (Stage 2-3, and this same session's
subtitle-track work) is a real, live-proven mechanism for *testing
timing and content* against an emulator, but it is not itself
shippable -- a burned disc has no host machine running an overlay
window next to it. The real deliverable path is offline and
disc-resident: decode a frame (`gcrts.movie_str_audio` + FFmpeg's
`psxstr`/`mdec` support), edit its pixels, re-encode back into a real
PS1 MDEC/`.STR` bitstream via `gcrts.movie_str_encoder` (`psxavenc`),
and patch it into a disc image copy (`gcrts.movie_subtitle_burner`) --
the same pattern Stage 4 already proved for dialogue text, all
`CONFIRMED_LIVE` this session (`evidence/burned_in_subtitle_live_playback/`,
`evidence/full_track_burned_in_live_proof/`).

**Word-wrap, added after a real legibility bug was found in that same
live proof**: the first live screenshots showed placeholder text
running off both edges of the 320px-wide frame, cut off and illegible
(`burn_subtitle_onto_frame` originally just centered whatever text it
was given on one line, with no width check at all). This version wraps
text to fit within `max_width_ratio` of the frame's actual width using
the real font's own measured glyph widths (never an assumed average
character width), stacking wrapped lines above the bottom margin. A
single word wider than the frame on its own is left unbroken rather
than hyphenated (standard subtitle convention) -- that's a genuine
authoring problem (the line needs rewording), not something this
function should silently paper over.

Font size default (18px in a 240px-tall frame) is in the same range as
this game's own native glyph cell (16x16, see `gcrts.glyph_atlas`) --
deliberately close to the resolution the game's own text was designed
to be legible at, rather than an arbitrary host-font size. Reusing the
game's actual extracted glyph bitmaps directly (rather than a host
TrueType font) was considered but not done here: that font's
compressed glyph data lives in a per-chapter RAM-resident resource
blob (`gcrts.glyph_atlas`'s own docstring), not something resolvable
from a disc file alone -- a real option for a future pass, not a
requirement for this one.
"""
from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont


def _load_font(font_size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("arial.ttf", font_size)
    except OSError:
        return ImageFont.load_default()


def _text_width(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def wrap_text_to_width(text: str, font, draw: ImageDraw.ImageDraw, max_width: int) -> list[str]:
    """Greedy word-wrap using the font's own real measured widths (never
    an assumed average character width). A single word wider than
    `max_width` on its own is kept whole on its own line rather than
    split -- standard subtitle convention; that's an authoring problem
    to reword, not something to hyphenate silently.

    A literal `\\n` in `text` forces a line break at that point (e.g. a
    title and its translated subtitle on their own intentional lines)
    -- each resulting segment is still word-wrapped independently in
    case it's too wide on its own."""
    if "\n" in text:
        lines: list[str] = []
        for segment in text.split("\n"):
            lines.extend(wrap_text_to_width(segment, font, draw, max_width))
        return lines

    words = text.split()
    if not words:
        return [text] if text else []

    lines = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if _text_width(draw, candidate, font) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def burn_subtitle_onto_frame(
    frame: Image.Image,
    text: str,
    font_size: int = 18,
    margin_bottom: int = 18,
    max_width_ratio: float = 0.92,
    line_spacing: int = 4,
    fill=(255, 255, 255),
    outline=(0, 0, 0),
) -> Image.Image:
    """Returns a NEW image (the input is never modified in place) with
    `text` word-wrapped to fit within `max_width_ratio` of the frame's
    width, drawn centered near the bottom (wrapped lines stack upward
    from `margin_bottom`), white-on-black-outline in the conventional
    subtitle style. Falls back to PIL's built-in bitmap font if no
    TrueType font is available on the host -- still correct, just less
    crisp, never an error."""
    result = frame.convert("RGB").copy()
    draw = ImageDraw.Draw(result)
    width, height = result.size

    font = _load_font(font_size)
    max_width = int(width * max_width_ratio)
    lines = wrap_text_to_width(text, font, draw, max_width)

    line_heights = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_heights.append(bbox[3] - bbox[1])
    total_height = sum(line_heights) + line_spacing * (len(lines) - 1 if lines else 0)

    y = height - total_height - margin_bottom
    for line, line_height in zip(lines, line_heights):
        line_width = _text_width(draw, line, font)
        x = (width - line_width) // 2
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx or dy:
                    draw.text((x + dx, y + dy), line, font=font, fill=outline)
        draw.text((x, y), line, font=font, fill=fill)
        y += line_height + line_spacing

    return result
