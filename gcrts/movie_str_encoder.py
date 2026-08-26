"""Re-encodes an edited frame sequence + audio back into a real,
PS1-compatible MDEC/STR bitstream via `psxavenc` -- the encoder half
`gcrts.movie_str_audio` (decode-only) can't do. Closes the gap
`docs/renderer/BURNED_IN_SUBTITLE_PIPELINE.md` originally left open;
see that doc and `evidence/burned_in_subtitle_live_playback/` for the
full live-verified account (a real burned-in subtitle rendering
correctly during real movie playback from a disc-patched copy).

`psxavenc` (https://github.com/WonderfulToolchain/psxavenc) is a real,
actively-maintained, third-party PS1 audio/video encoder -- NOT part
of this project, not vendored into the repo, and not a pip package.
Download the prebuilt Windows binary from its GitHub releases (e.g.
`psxavenc-windows.zip` from a release tag) and pass its `psxavenc.exe`
path to `encode_str`. FFmpeg's own `mdec`/`psxstr` support (used
elsewhere in this project, e.g. `gcrts.movie_str_audio`) is decode-only
and cannot substitute for this.

CONFIRMED LIVE this session with `psxavenc`'s default options
(`-t strcd -f 37800 -c 2 -s 320x240 -r 15`, matching this game's own
real `OP.STR` stream properties exactly) -- a real disc-patched,
re-encoded movie with burned-in text played back correctly and
visibly on a live emulator instance. Options were not tuned or
compared (BS v2 vs v3, quality/bitrate) beyond what worked.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


class PsxavencError(RuntimeError):
    pass


def encode_str(
    psxavenc_exe: str | Path,
    input_video_path: str | Path,
    output_str_path: str | Path,
    *,
    sample_rate: int = 37800,
    channels: int = 2,
    size: str = "320x240",
    fps: int = 15,
    format: str = "strcd",
) -> None:
    """`input_video_path` must be a container FFmpeg/psxavenc can
    decode (a real video codec, not raw frames) -- build it first via
    a normal ffmpeg mux of an edited frame sequence + audio (see
    `docs/renderer/BURNED_IN_SUBTITLE_PIPELINE.md` for the exact
    commands used this session). `format='strcd'` (2352-byte sectors,
    matching a raw disc-image read/patch) is the right choice for
    building something to patch into a disc copy via
    `gcrts.disc_text_patch.build_patched_disc_copy`; `'str'` (2336-byte
    sectors) is for filesystem-level authoring tools that add the
    sync/header themselves."""
    result = subprocess.run(
        [
            str(psxavenc_exe),
            "-t", format,
            "-f", str(sample_rate),
            "-c", str(channels),
            "-s", size,
            "-r", str(fps),
            str(input_video_path),
            str(output_str_path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise PsxavencError(f"psxavenc failed (exit {result.returncode}):\n{result.stderr[-2000:]}")
