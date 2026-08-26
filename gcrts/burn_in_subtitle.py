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
`psxstr`/`mdec` support, already proven this session), edit its
pixels, then (not yet built -- see module docstring below) re-encode
back into a real PS1 MDEC/`.STR` bitstream and patch it into a disc
image copy, the same pattern Stage 4 already proved for dialogue text.

**This module only does the pixel-editing step.** Confirmed live this
session (`evidence/burned_in_subtitle_concept/`): a real frame decoded
from `OP.STR` with "-insert text here-" burned in, readable, correctly
positioned like a real subtitle. **What remains unbuilt and unproven**:
re-encoding an edited frame sequence back into a bitstream the PS1's
own MDEC hardware/BIOS movie player actually accepts. FFmpeg's own
`mdec` support is decode-only (no PS1-compatible encoder exists in
stock FFmpeg) -- a real PS1 STR/MDEC encoder (community tools like
`psxavenc` exist but have not been evaluated in this project as of
2026-08-26) would be needed before this pixel-editing step can produce
anything that plays on a real console or a plain emulator without this
project's own live tooling running alongside it.
"""
from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont


def burn_subtitle_onto_frame(
    frame: Image.Image,
    text: str,
    font_size: int = 18,
    margin_bottom: int = 18,
    fill=(255, 255, 255),
    outline=(0, 0, 0),
) -> Image.Image:
    """Returns a NEW image (the input is never modified in place) with
    `text` drawn centered near the bottom, white-on-black-outline in
    the conventional subtitle style. Falls back to PIL's built-in
    bitmap font if no TrueType font is available on the host -- still
    correct, just less crisp, never an error."""
    result = frame.convert("RGB").copy()
    draw = ImageDraw.Draw(result)
    width, height = result.size

    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except OSError:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (width - text_width) // 2
    y = height - text_height - margin_bottom

    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx or dy:
                draw.text((x + dx, y + dy), text, font=font, fill=outline)
    draw.text((x, y), text, font=font, fill=fill)

    return result
