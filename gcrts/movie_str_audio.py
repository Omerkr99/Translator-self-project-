"""Extracts the audio track from a real PS1 `.STR` movie file via
FFmpeg's `psxstr` demuxer -- the same approach and the same
independently-verified decoder path this project already used to
validate its own XA-ADPCM decoder against reference output
(`docs/audio/XA_DECODER_VERIFICATION.md`). A `.STR` movie is a
standard, well-known container (unlike `XAPACK`'s custom multi-channel
format this project reverse-engineered by hand) -- FFmpeg's `psxstr`
demuxer auto-detects it directly from the *raw* disc bytes (sync +
header + subheader intact, no reformatting), confirmed live this
session against the real `OP.STR` file: it reported exactly
`Video: mdec, yuvj420p(pc), 320x240, 15 fps` and
`Audio: adpcm_xa, 37800 Hz, stereo, s16p`, matching this project's own
already-established XA sample rate/channel findings.

Requires `imageio_ffmpeg` (already a project dependency via other
audio-verification work) for a bundled, independent FFmpeg binary --
no ffmpeg install assumed on the host.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import imageio_ffmpeg


def read_raw_str_bytes(disc_path: str | Path, lba: int, logical_size: int, sector_size: int = 2352, logical_sector_size: int = 2048) -> bytes:
    """Reads a movie file's exact raw physical bytes (sync+header+
    subheader intact) directly from a disc image -- NOT via
    `gcrts.iso9660.read_file()`, which extracts only the 2048-byte
    logical payload per sector and would strip the CD-XA subheader
    flags FFmpeg's psxstr demuxer needs to tell video/audio sectors
    apart. `logical_size` is the ISO9660 directory entry's own file
    size (e.g. `gcrts.movie_detection.MovieFileEntry.size`), which
    divides evenly by 2048 for every real entry checked so far."""
    if logical_size % logical_sector_size != 0:
        raise ValueError(f"logical_size {logical_size} is not a multiple of {logical_sector_size} -- LBA/size math assumption doesn't hold for this entry")
    num_sectors = logical_size // logical_sector_size
    physical_offset = lba * sector_size
    length = num_sectors * sector_size
    with open(disc_path, "rb") as f:
        f.seek(physical_offset)
        data = f.read(length)
    if len(data) != length:
        raise ValueError(f"short read: expected {length} bytes at offset {physical_offset}, got {len(data)}")
    return data


def extract_str_audio_wav(raw_str_bytes: bytes, out_wav_path: str | Path) -> None:
    """Demuxes `raw_str_bytes` (the exact bytes `read_raw_str_bytes`
    returns) via FFmpeg's `psxstr` input format and writes the decoded
    audio track as a 16-bit PCM WAV file. Writes the raw bytes to a
    temporary file first -- FFmpeg's psxstr demuxer needs a real
    seekable file, not a pipe, to probe the stream layout correctly."""
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    out_wav_path = Path(out_wav_path)
    tmp_raw_path = out_wav_path.with_suffix(".raw_str_tmp.bin")
    tmp_raw_path.write_bytes(raw_str_bytes)
    try:
        result = subprocess.run(
            [ffmpeg, "-y", "-f", "psxstr", "-i", str(tmp_raw_path), "-vn", "-c:a", "pcm_s16le", "-f", "wav", str(out_wav_path)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg failed (exit {result.returncode}):\n{result.stderr[-2000:]}")
    finally:
        tmp_raw_path.unlink(missing_ok=True)
